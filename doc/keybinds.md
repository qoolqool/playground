# Neovim Keybinds

Custom keymaps from [`keymaps.lua`](../tooling/config/nvim/lua/config/keymaps.lua).

## File Explorer (nvim-tree)

| Key | Action |
|-----|--------|
| `Ctrl-n` | Toggle file tree sidebar |
| `Ctrl-f` | Reveal current file in tree |

## Fuzzy Finder (Telescope)

| Key | Action |
|-----|--------|
| `Ctrl-p` | Find files |
| `Ctrl-b` | Switch buffers |

## Buffer Navigation

| Key | Action |
|-----|--------|
| `Leader 1`–`9` | Jump to buffer 1–9 |
| `Leader bn` | Next buffer |
| `Leader bp` | Previous buffer |
| `Leader Tab` | Alternate buffer (switch to last) |
| `Leader bd` | Close buffer |
| `Leader ba` | Close all buffers |

## Quick File Operations

| Key | Action |
|-----|--------|
| `Leader o` | Open file (type path) |
| `Leader e` | Netrw Explorer |

## Split Management

| Key | Action |
|-----|--------|
| `Leader s\|` | Vertical split |
| `Leader s-` | Horizontal split |
| `Ctrl-h/j/k/l` | Navigate between splits |
| `Ctrl-Arrow` | Resize split |

## Search & Replace

| Key | Action |
|-----|--------|
| `Leader /` | Forward search |
| `Leader r` | Search & replace (`:%s/`) |
| `Esc Esc` | Clear search highlight |

## Commenting (Comment.nvim)

| Key | Action |
|-----|--------|
| `Ctrl-/` / `Ctrl-_` | Toggle comment (normal + visual) |

## Git (fugitive)

| Key | Action |
|-----|--------|
| `Leader gs` | `:Git status` |
| `Leader gc` | `:Git commit` |
| `Leader gp` | `:Git push` |
| `Leader gf` | `:Gfetch` |
| `Leader gl` | `:Git log` |
| `Leader gd` | `:Gdiffsplit` |
| `Leader gb` | `:Git blame` |

## LSP (auto-bound on attach)

| Key | Action |
|-----|--------|
| `gd` | Go to definition |
| `gy` | Go to type definition |
| `gi` | Go to implementation |
| `gr` | Go to references |
| `K` | Hover documentation |
| `Leader rn` | Rename symbol |
| `Leader f` | Format code |

## Other

| Key | Action |
|-----|--------|
| `Leader m` | Show marks |
| `Leader vrn` | Toggle relative line numbers |
| `Leader tw` | Toggle soft wrap *(markdown only)* |