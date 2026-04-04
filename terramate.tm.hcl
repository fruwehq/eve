terramate {
  required_version = "~> 0.16.0"

  config {
    git {
      default_branch = "main"
    }

    run {
      env {
        TF_PLUGIN_CACHE_DIR = "${terramate.root.path.fs.absolute}/.terraform-cache-dir/plugins"
        TF_DATA_DIR         = "${terramate.root.path.fs.absolute}/.terraform-cache-dir/data/${terramate.stack.path.relative}"
        TF_VAR_my_ip        = env.MY_IP
      }
    }
  }
}
