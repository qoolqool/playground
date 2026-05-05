return {
  "MeanderingProgrammer/render-markdown.nvim",
  ft = "markdown",
  config = function()
    require("render-markdown").setup({
      file_types = { "markdown" },
      anti_conceal = { enabled = false },
      -- Enable mermaid diagram rendering
      mermaid = {
        enabled = true,
      },
    })

    -- Markdown keymaps
    local map = vim.keymap.set
    map("n", "<leader>mt", ":RenderMarkdown toggle<CR>", { desc = "Toggle markdown render" })
    map("n", "<leader>mh", ":RenderMarkdown toggle_heading<CR>", { desc = "Toggle heading icons" })
    map("n", "<leader>mb", ":RenderMarkdown toggle_bullet<CR>", { desc = "Toggle bullet icons" })
  end
}
