local map = vim.keymap.set
local opts = { noremap = true, silent = true }

-- File explorer (nvim-tree)
map("n", "<C-n>", ":NvimTreeToggle<CR>", opts)
map("n", "<C-f>", ":NvimTreeFindFile<CR>", opts)

-- Fuzzy finder (telescope)
map("n", "<C-p>", ":Telescope find_files<CR>", opts)
map("n", "<C-b>", ":Telescope buffers<CR>", opts)

-- Buffer navigation
for i = 1, 9 do
  map("n", "<leader>" .. i, ":b" .. i .. "<CR>", opts)
end
map("n", "<leader>bn", ":bnext<CR>", opts)
map("n", "<leader>bp", ":bprevious<CR>", opts)
map("n", "<leader><Tab>", ":b#<CR>", opts)
map("n", "<leader>bd", ":bdelete<CR>", opts)
map("n", "<leader>ba", ":%bd!<CR>", opts)

-- Quick file operations
map("n", "<leader>o", ":e ", opts)
map("n", "<leader>e", ":Explore<CR>", opts)

-- Split management
map("n", "<leader>s|", ":vsplit<CR><C-w>l", opts)
map("n", "<leader>s-", ":split<CR><C-w>j", opts)
map("n", "<C-h>", "<C-w>h", opts)
map("n", "<C-j>", "<C-w>j", opts)
map("n", "<C-k>", "<C-w>k", opts)
map("n", "<C-l>", "<C-w>l", opts)
map("n", "<C-Up>", "<C-w>+", opts)
map("n", "<C-Down>", "<C-w>-", opts)
map("n", "<C-Left>", "<C-w><", opts)
map("n", "<C-Right>", "<C-w>>", opts)

-- Marks
map("n", "<leader>m", ":marks<CR>", opts)

-- Search
map("n", "<leader>/", "/", opts)
map("n", "<leader>r", ":%s/", opts)

-- Commenting (Comment.nvim gcc/gbc)
map("n", "<C-_>", "gcc", { remap = true })
map("v", "<C-_>", "gc", { remap = true })
map("n", "<C-/>", "gcc", { remap = true })
map("v", "<C-/>", "gc", { remap = true })

-- Git (fugitive)
map("n", "<leader>gs", ":Git status<CR>", opts)
map("n", "<leader>gc", ":Git commit<CR>", opts)
map("n", "<leader>gp", ":Git push<CR>", opts)
map("n", "<leader>gf", ":Gfetch<CR>", opts)
map("n", "<leader>gl", ":Git log<CR>", opts)
map("n", "<leader>gd", ":Gdiffsplit<CR>", opts)
map("n", "<leader>gb", ":Git blame<CR>", opts)

-- Clear search highlight
map("n", "<Esc><Esc>", ":nohlsearch<CR>", opts)

-- Toggle relative line numbers
map("n", "<leader>vrn", ":set relativenumber!<CR>", opts)

-- Markdown toggle wrap
vim.api.nvim_create_autocmd("FileType", {
  pattern = "markdown",
  callback = function()
    local bopts = { buffer = true }
    map("n", "<leader>tw", ":setlocal wrap!<CR>", bopts)
    vim.opt_local.textwidth = 0
    vim.opt_local.wrap = false
    vim.opt_local.linebreak = true
    vim.opt_local.list = false
  end,
})

-- LSP keymaps (set on attach)
vim.api.nvim_create_autocmd("LspAttach", {
  callback = function(args)
    local bopts = { buffer = args.buf, silent = true }
    map("n", "gd", vim.lsp.buf.definition, vim.tbl_extend("force", bopts, { desc = "Go to definition" }))
    map("n", "gy", vim.lsp.buf.type_definition, vim.tbl_extend("force", bopts, { desc = "Go to type definition" }))
    map("n", "gi", vim.lsp.buf.implementation, vim.tbl_extend("force", bopts, { desc = "Go to implementation" }))
    map("n", "gr", vim.lsp.buf.references, vim.tbl_extend("force", bopts, { desc = "Go to references" }))
    map("n", "K", vim.lsp.buf.hover, vim.tbl_extend("force", bopts, { desc = "Show documentation" }))
    map("n", "<leader>rn", vim.lsp.buf.rename, vim.tbl_extend("force", bopts, { desc = "Rename symbol" }))
    map("n", "<leader>f", function() vim.lsp.buf.format({ async = true }) end, vim.tbl_extend("force", bopts, { desc = "Format code" }))
  end,
})