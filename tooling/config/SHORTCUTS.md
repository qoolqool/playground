# Neovim Keymaps

## General
| Key | Action |
|-----|--------|
| `<leader>` = Space |
| `<C-n>` | Toggle file tree |
| `<C-p>` | Find files (Telescope) |
| `<C-f>` | Live grep (Telescope) |
| `<Esc><Esc>` | Clear search highlight |

## Buffers
| Key | Action |
|-----|--------|
| `<leader>bn` | Next buffer |
| `<leader>bp` | Previous buffer |
| `<leader>bd` | Delete buffer |

## Windows
| Key | Action |
|-----|--------|
| `<leader>sv` | Vertical split |
| `<leader>sh` | Horizontal split |

## Linting & Diagnostics
| Key | Action |
|-----|--------|
| `<leader>l` | Run linter |
| `<leader>ld` | Open diagnostics list |
| `[d` | Previous diagnostic |
| `]d` | Next diagnostic |
| `<leader>d` | Show diagnostic popup |

## LSP
| Key | Action |
|-----|--------|
| `gd` | Go to definition |
| `gr` | Find references |
| `K` | Hover (show docs) |
| `<leader>rn` | Rename symbol |

## Markdown (render-markdown.nvim)
| Key | Action |
|-----|--------|
| `<leader>mt` | Toggle markdown render |
| `<leader>mh` | Toggle heading icons |
| `<leader>mb` | Toggle bullet icons |

## Mermaid Diagrams
| Key | Action |
|-----|--------|
| `<leader>mp` | Preview mermaid diagram (inline or browser) |
| `<leader>mr` | Refresh preview |
| `<leader>mi` | Install mermaid CLI |

## Images (image.nvim)
Works in Warp terminal with kitty protocol.
Automatically renders images in markdown files.
