local opt = vim.opt
local g = vim.g

-- Disable netrw (nvim-tree handles file browsing)
g.loaded_netrw = 1
g.loaded_netrwPlugin = 1

-- Line numbers
opt.number = true
opt.relativenumber = true

-- Indentation
opt.expandtab = true
opt.tabstop = 4
opt.shiftwidth = 4
opt.softtabstop = 4
opt.autoindent = true
opt.smartindent = true

-- Editing
opt.mouse = "a"
opt.clipboard = "unnamedplus"
opt.hidden = true
opt.backup = false
opt.writebackup = false
opt.undofile = true

-- Search
opt.ignorecase = true
opt.smartcase = true
opt.incsearch = true
opt.hlsearch = true

-- UI
opt.cursorline = true
opt.wrap = true
opt.breakindent = true
opt.signcolumn = "yes"
opt.cmdheight = 2
opt.conceallevel = 0
opt.background = "dark"
opt.termguicolors = true

-- Encoding
opt.encoding = "utf-8"
opt.fileencoding = "utf-8"

-- Performance
opt.updatetime = 100
opt.ttimeoutlen = 0
opt.timeoutlen = 1000
opt.lazyredraw = true
opt.shortmess:append("c")

-- Diff
opt.diffopt:append({ "algorithm:histogram", "indent-heuristic" })

-- Session
opt.viewoptions = { "slash", "unix" }

-- Filetype
vim.cmd("filetype plugin indent on")
vim.cmd("syntax enable")