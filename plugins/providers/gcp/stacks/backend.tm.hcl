generate_hcl "z_backend.tf" {
  content {
    terraform {
      backend "local" {}
    }
  }
}
