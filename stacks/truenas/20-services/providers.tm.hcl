generate_hcl "z_providers.tf" {
  content {
    terraform {
      required_providers {
        truenas = {
          source  = "deevus/truenas"
          version = "0.16.0"
        }
        null = {
          source  = "hashicorp/null"
          version = "~> 3.0"
        }
      }
    }

    variable "truenas_auth_method" {
      type    = string
      default = "ssh"
    }

    variable "truenas_host" {
      type = string
    }

    variable "truenas_ssh_host_key_fingerprint" {
      type = string
    }

    variable "truenas_ssh_port" {
      type    = number
      default = 22
    }

    variable "truenas_ssh_private_key_file" {
      type = string
    }

    variable "truenas_ssh_user" {
      type    = string
      default = "terraform"
    }

    provider "truenas" {
      auth_method = var.truenas_auth_method
      host        = var.truenas_host

      ssh {
        host_key_fingerprint = var.truenas_ssh_host_key_fingerprint
        port                 = var.truenas_ssh_port
        private_key          = file(var.truenas_ssh_private_key_file)
        user                 = var.truenas_ssh_user
      }
    }
  }
}
