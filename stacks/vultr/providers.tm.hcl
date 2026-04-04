# This file is part of Terramate Configuration.
# Terramate is an orchestrator and code generator for Terraform.
# Please see https://github.com/mineiros-io/terramate for more information.
#
# To generate/update Terraform code within the stacks
# run `terramate generate` from root directory of the repository.

##############################################################################
# Generate 'z_providers.tf' in each stack
# All globals will be replaced with the final value that is known by the stack
# Any terraform code can be defined within the content block
generate_hcl "z_providers.tf" {
  content {
    terraform {
      required_providers {
        vultr = {
          source  = "vultr/vultr"
          version = "2.30.1"
        }
      }

      required_version = global.terraform_version
    }

    provider "vultr" {
      api_key = "VULTR_API_KEY"
    }
  }
}
