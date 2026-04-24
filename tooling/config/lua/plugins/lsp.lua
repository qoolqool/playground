return {
  "neovim/nvim-lspconfig",
  config = function()
    -- Check for new vim.lsp.config() API (nvim 0.11+)
    local function setup_lsp(name, opts)
      if vim.lsp.config then
        -- New API (suppresses deprecation warning)
        vim.lsp.config(name, opts)
      else
        -- Legacy API
        require("lspconfig")[name].setup(opts)
      end
    end

    -- Setup LSP servers
    setup_lsp("pyright", {})
    setup_lsp("lua_ls", {})
    setup_lsp("sqlls", {})

    -- LSP Attach Keymaps
    vim.api.nvim_create_autocmd("LspAttach", {
      callback = function(ev)
        local map = vim.keymap.set
        local opts = { buffer = ev.buf }

        map("n", "gd", vim.lsp.buf.definition, opts)
        map("n", "gr", vim.lsp.buf.references, opts)
        map("n", "K", vim.lsp.buf.hover, opts)
        map("n", "<leader>rn", vim.lsp.buf.rename, opts)
      end,
    })
  end
}
