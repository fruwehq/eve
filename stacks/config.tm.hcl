# This file is part of Terramate Configuration.
# Terramate is an orchestrator and code generator for Terraform.
# Please see https://github.com/mineiros-io/terramate for more information.
#
# To generate/update Terraform code within the stacks
# run `terramate generate` from root directory of the repository.

globals {
  ### GLOBAL INFO #############################################################

  ### TERRAFORM ###############################################################

  ### global variables for use when generating providers
  # all variables defined here can be overwritten in any sub-directory and on the
  # stack level

  # The global terraform version to use
  terraform_version = "~> 1.14.8"

  # THe project name
  project = "ephemeral-cloud-gaming"
}
