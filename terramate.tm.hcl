terramate {
  required_version = "~> 0.16.0"

  config {
    git {
      default_branch = "main"
    }

    run {
      env {
        TF_PLUGIN_CACHE_DIR        = "${terramate.root.path.fs.absolute}/.terraform-cache-dir/plugins"
        TF_DATA_DIR                = "${tm_try(env.EGAME_TF_DATA_BASE, "${terramate.root.path.fs.absolute}/.terraform-cache-dir/data")}/${terramate.stack.path.relative}"
        TF_VAR_my_ip               = env.MY_IP
        TF_VAR_ssh_public_key_file = env.SSH_PUBLIC_KEY_FILE
      }
    }
  }
}
