return {
  -- Colorscheme
  {
    "ellisonleao/gruvbox.nvim",
    priority = 1000,
    config = function()
      require("gruvbox").setup({ contrast = "hard" })
      vim.cmd.colorscheme("gruvbox")
    end,
  },

  -- Icons (dependency for other plugins)
  { "nvim-tree/nvim-web-devicons" },

  -- Git
  { "tpope/vim-fugitive" },
  { "tpope/vim-rhubarb" },
  {
    "lewis6991/gitsigns.nvim",
    config = function()
      require("gitsigns").setup({
        signs = {
          add = { text = "▌" },
          change = { text = "▌" },
          delete = { text = "▌" },
        },
      })
    end,
  },

  -- File explorer
  {
    "nvim-tree/nvim-tree.lua",
    cmd = { "NvimTreeToggle", "NvimTreeFindFile" },
    config = function()
      require("nvim-tree").setup({
        view = { width = 30 },
        renderer = {
          group_empty = true,
          icons = { show = { git = true, folder = true, file = true } },
        },
        filters = {
          custom = {
            "^\\.git$", "^\\.pyc$", "__pycache__",
            "node_modules", "^\\.egg-info$", "^\\.pytest_cache$",
          },
        },
        actions = { open_file = { quit_on_open = true } },
      })
      vim.api.nvim_create_autocmd("BufEnter", {
        nested = true,
        callback = function()
          if #vim.api.nvim_list_wins() == 1 and vim.bo.buftype == "nofile" and vim.bo.filetype == "NvimTree" then
            vim.cmd("quit")
          end
        end,
      })
    end,
  },

  -- Fuzzy finder
  {
    "nvim-telescope/telescope.nvim",
    cmd = { "Telescope" },
    dependencies = { "nvim-lua/plenary.nvim" },
    config = function()
      require("telescope").setup({
        defaults = {
          file_ignore_patterns = {
            "node_modules", "%.git/", "__pycache__",
            "%.egg-info", "%.pytest_cache", "build", "dist",
          },
        },
      })
    end,
  },

  -- Status line
  {
    "nvim-lualine/lualine.nvim",
    event = "VeryLazy",
    config = function()
      require("lualine").setup({
        options = {
          theme = "gruvbox",
          section_separators = "",
          component_separators = "",
        },
        sections = {
          lualine_c = { { "filename", path = 1 } },
        },
      })
    end,
  },

  -- LSP (servers pre-installed globally in the Docker image)
  {
    "neovim/nvim-lspconfig",
    event = { "BufReadPre", "BufNewFile" },
    dependencies = {
      "williamboman/mason.nvim",
      "hrsh7th/cmp-nvim-lsp",
    },
    config = function()
      require("mason").setup()
      local capabilities = require("cmp_nvim_lsp").default_capabilities()

      vim.lsp.config("pyright", {
        capabilities = capabilities,
      })

      vim.lsp.config("lua_ls", {
        capabilities = capabilities,
        settings = {
          Lua = {
            runtime = { version = "LuaJIT" },
            workspace = { checkThirdParty = false },
            diagnostics = { globals = { "vim" } },
          },
        },
      })

      vim.lsp.enable({ "pyright", "lua_ls" })
    end,
  },

  -- Completion
  {
    "hrsh7th/nvim-cmp",
    event = "InsertEnter",
    dependencies = {
      "hrsh7th/cmp-nvim-lsp",
      "hrsh7th/cmp-buffer",
      "hrsh7th/cmp-path",
    },
    config = function()
      local cmp = require("cmp")
      cmp.setup({
        mapping = cmp.mapping.preset.insert({
          ["<Tab>"] = cmp.mapping.select_next_item(),
          ["<S-Tab>"] = cmp.mapping.select_prev_item(),
          ["<CR>"] = cmp.mapping.confirm({ select = true }),
          ["<C-Space>"] = cmp.mapping.complete(),
        }),
        sources = {
          { name = "nvim_lsp" },
          { name = "buffer" },
          { name = "path" },
        },
      })
    end,
  },

  -- Treesitter
  {
    "nvim-treesitter/nvim-treesitter",
    build = ":TSUpdate",
    event = { "BufReadPre", "BufNewFile" },
    config = function()
      -- nvim-treesitter v1.0+: the configs module was removed.
      -- Highlighting and indentation are enabled automatically by Neovim
      -- when parsers are installed. Use :TSInstall to add parsers.
      -- Disable treesitter highlighting for markdown (render-markdown handles it).
      vim.api.nvim_create_autocmd("FileType", {
        pattern = "markdown",
        callback = function()
          vim.treesitter.stop()
        end,
      })
    end,
  },

  -- Editing
  {
    "numToStr/Comment.nvim",
    keys = { { "gcc", mode = "n" }, { "gc", mode = "v" } },
    config = function() require("Comment").setup() end,
  },
  {
    "echasnovski/mini.surround",
    version = false,
    config = function() require("mini.surround").setup() end,
  },
  {
    "echasnovski/mini.ai",
    version = false,
    config = function() require("mini.ai").setup() end,
  },
  {
    "windwp/nvim-autopairs",
    event = "InsertEnter",
    config = function() require("nvim-autopairs").setup() end,
  },

  -- Markdown
  {
    "MeanderingProgrammer/render-markdown.nvim",
    ft = "markdown",
    config = function()
      require("render-markdown").setup({
        render_modes = { "n", "c" },
        latex = { enabled = false },
        anti_conceal = { enabled = false },
        heading = {
          enabled = true,
          sign = false,
          icons = { "# ", "## ", "### ", "#### ", "##### ", "###### " },
        },
        code = { enabled = true, sign = false },
        list = {
          enabled = true,
          icons = { "● ", "○ ", "■ ", "□ " },
        },
        table = { enabled = true, preset = "none", style = "normal" },
        indent = { enabled = true, per_level = 2 },
      })
    end,
  },
}