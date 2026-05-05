-- Markdown wrap handling (treesitter-aware, lazy-loaded)
local function md_wrap()
  local ok, ts_utils = pcall(require, "nvim-treesitter.ts_utils")
  if not ok then
    vim.wo.wrap = true
    return
  end

  local node = ts_utils.get_node_at_cursor()
  while node do
    local t = node:type()
    if t == "pipe_table" or t == "table" then
      vim.wo.wrap = false
      return
    end
    node = node:parent()
  end
  vim.wo.wrap = true
end

vim.api.nvim_create_autocmd("CursorMoved", {
  pattern = "*.md",
  callback = md_wrap,
})
