# This file is part of Terramate Configuration.
# Terramate is an orchestrator and code generator for Terraform.
# Please see https://github.com/mineiros-io/terramate for more information.
#
# To generate/update Terraform code within the stacks
# run `terramate generate` from root directory of the repository.

##############################################################################
# Generate 'z_backend.tf' in each stack
# All globals will be replaced with the final value that is known by the stack
# Any terraform code can be defined within the content block
generate_hcl "z_backend.tf" {
  content {
    terraform {

      backend "local" {
        path = "${terramate.root.path.fs.absolute}/.terraform-cache-dir/state/${terramate.stack.path.relative}/terraform.tfstate"
      }
    }
  }
}
