return {
  "2kabhishek/mermaid.nvim",
  dependencies = {
    "nvim-lua/plenary.nvim",
  },
  build = function()
    vim.fn["mermaid#install"]()
  end,
  config = function()
    require("mermaid").setup({
      auto_preview = false,
      render_method = "img",  -- Try inline image first
      keymaps = {
        preview = "<leader>mp",
        refresh = "<leader>mr",
        install = "<leader>mi",
      },
    })
  end
}
