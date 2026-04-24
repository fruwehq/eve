# This file is part of Terramate Configuration.
# Terramate is an orchestrator and code generator for Terraform.
# Please see https://github.com/mineiros-io/terramate for more information.
#
# To generate/update Terraform code within the stacks
# run `terramate generate` from root directory of the repository.

generate_hcl "z_backend.tf" {
  content {
    terraform {
      backend "local" {
        path = "${terramate.root.path.fs.absolute}/.terraform-cache-dir/state/${terramate.stack.path.relative}/terraform.tfstate"
      }
    }
  }
}
