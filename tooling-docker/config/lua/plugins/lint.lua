return {
  "mfussenegger/nvim-lint",
  config = function()
    local lint = require("lint")

    -- Configure linters per filetype
    lint.linters_by_ft = {
      python = { "pylint" },
      lua = { "luacheck" },
      bash = { "shellcheck" },
      dockerfile = { "hadolint" },
      yaml = { "yamllint" },
      json = { "jsonlint" },
      markdown = { "markdownlint" },
    }

    -- Autocmd to lint on save
    vim.api.nvim_create_autocmd({ "BufWritePost" }, {
      callback = function()
        -- Use try_lint to avoid errors if linter not installed
        lint.try_lint()
      end,
    })
  end
}
