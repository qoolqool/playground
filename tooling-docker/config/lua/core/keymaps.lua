local map = vim.keymap.set
local opts = { silent = true }

-- Leader
vim.g.mapleader = " "

-- File explorer
map("n", "<C-n>", ":NvimTreeToggle<CR>", opts)

-- Telescope
map("n", "<C-p>", "<cmd>Telescope find_files<CR>", opts)
map("n", "<C-f>", "<cmd>Telescope live_grep<CR>", opts)

-- Buffers
map("n", "<leader>bn", ":bnext<CR>", opts)
map("n", "<leader>bp", ":bprev<CR>", opts)
map("n", "<leader>bd", ":bdelete<CR>", opts)

-- Splits
map("n", "<leader>sv", ":vsplit<CR>", opts)
map("n", "<leader>sh", ":split<CR>", opts)

-- Clear search
map("n", "<Esc><Esc>", ":nohlsearch<CR>", opts)

-- Linting (only if nvim-lint is installed)
map("n", "<leader>l", function()
  local ok, lint = pcall(require, "lint")
  if ok then lint.try_lint() else print("nvim-lint not installed") end
end, { desc = "Run linter" })
map("n", "<leader>ld", vim.diagnostic.setloclist, { desc = "Open diagnostics list" })

-- Diagnostics navigation
map("n", "[d", vim.diagnostic.goto_prev, { desc = "Previous diagnostic" })
map("n", "]d", vim.diagnostic.goto_next, { desc = "Next diagnostic" })
map("n", "<leader>d", vim.diagnostic.open_float, { desc = "Show diagnostic" })
