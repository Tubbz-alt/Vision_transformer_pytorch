import torch
import torch.nn as nn


class MLP(nn.Module):
    def __init__(self, in_features, hidden_features=None, out_features=None,
                 dropout=0.):
        super().__init__()
        if not hidden_features:
            hidden_features = in_features
        if not out_features:
            out_features = in_features
        self.fc1 = nn.Linear(in_features, hidden_features)
        self.actn = nn.GELU()
        self.fc2 = nn.Linear(hidden_features, out_features)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        x = self.fc1(x)
        x = self.actn(x)
        x = self.fc2(x)
        return self.dropout(x)


class Attention(nn.Module):
    def __init__(self, dim, num_heads=8, attn_dropout=0., proj_dropout=0.):
        super().__init__()
        self.num_heads = num_heads
        self.scale = 1./dim**0.5

        self.qkv = nn.Linear(dim, dim*3, bias=False)
        self.attn_dropout = nn.Dropout(attn_dropout)
        self.out = nn.Sequential(
            nn.Linear(dim, dim),
            nn.Dropout(proj_dropout)
        )

    def forward(self, x, mask=None):
        b, n, c = x.shape
        qkv = self.qkv(x).reshape(b, n, 3, self.num_heads, c//self.num_heads)
        q, k, v = qkv.permute(2, 0, 3, 1, 4)
        dot = (q @ k.transpose(-2, -1)) * self.scale

        # TO-DO: APPLY MASK
        if mask is not None:
            print("Mask is yet to be implemented.")

        attn = dot.softmax(dim=-1)
        attn = self.attn_dropout(attn)

        x = (attn @ v).transpose(1, 2).reshape(b, n, c)
        x = self.out(x)
        return x


class ImgPatches(nn.Module):
    def __init__(self, patch_size=16):
        super().__init__()
        self.patch_size = patch_size

    def forward(self, img):
        b, c, h, w = img.shape
        patches = img.unfold(2, self.patch_size,
                             self.patch_size).unfold(3, self.patch_size,
                                                     self.patch_size)
        patches = patches.reshape(b, -1, c * self.patch_size * self.patch_size)
        return patches


class Block(nn.Module):
    def __init__(self, dim, num_heads=8, mlp_ratio=4, drop_rate=0.):
        super().__init__()
        self.ln1 = nn.LayerNorm(dim)
        self.attn = Attention(dim, num_heads, drop_rate, drop_rate)
        self.ln2 = nn.LayerNorm(dim)
        self.mlp = MLP(dim, dim*mlp_ratio, dropout=drop_rate)

    def forward(self, x, mask):
        x1 = self.ln1(x)
        x = x + self.attn(x1, mask)
        x2 = self.ln2(x)
        x = x + self.mlp(x2)
        return x


class Transformer(nn.Module):
    def __init__(self, depth, dim, num_heads=8, mlp_ratio=4, drop_rate=0.):
        super().__init__()
        self.blocks = nn.ModuleList([
            Block(dim, num_heads, mlp_ratio, drop_rate)
            for i in range(depth)])

    def forward(self, x, mask):
        for block in self.blocks:
            x = block(x, mask)
        return x


class ViT(nn.Module):
    def __init__(self, img_size=224, patch_size=16, in_ch=3, num_classes=1000,
                 use_mlp=True, embed_dim=768, depth=12, num_heads=12,
                 mlp_ratio=4, drop_rate=0.):
        super().__init__()
        if img_size % patch_size != 0:
            raise ValueError('Image size must be divisible by patch size.')
        num_patches = (img_size//patch_size) ** 2
        patch_dim = in_ch * patch_size * patch_size
        self.patch_size = patch_size

        # Image patches and embedding layer
        self.patches = ImgPatches(self.patch_size)
        self.patch_embed = nn.Linear(patch_dim, embed_dim)

        # Embedding for patch position and class
        self.pos_emb = nn.Parameter(torch.zeros(1, num_patches+1, embed_dim))
        self.cls_emb = nn.Parameter(torch.zeros(1, 1, embed_dim))

        self.transfomer = Transformer(depth, embed_dim, num_heads,
                                      mlp_ratio, drop_rate)
        self.norm = nn.LayerNorm(embed_dim)
        if use_mlp:
            self.out = MLP(embed_dim, embed_dim*mlp_ratio, num_classes)
        else:
            self.out = nn.Linear(embed_dim, num_classes)

    def forward(self, x, mask=None):
        b = x.shape[0]
        cls_token = self.cls_emb.expand(b, -1, -1)

        x = self.patch_embed(self.patches(x))
        x = torch.cat((cls_token, x), dim=1)
        x += self.pos_emb

        x = self.transfomer(x, mask)
        x = self.norm(x[:, 0])
        x = self.out(x)
        return x