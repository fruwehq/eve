stack {
  name = "301 Windows"

  tags = [
    "vultr",
    "services",
    "windows",
  ]

  after = [
    "/stacks/vultr/20-shared",
  ]
}

globals "vultr" "instance" {
  backups = "disabled"
  plan    = "vcg-a40-2c-10g-4vram"
  # plan    = "vcg-a40-4c-20g-8vram"
  # plan    = "vcg-a40-6c-30g-12vram"
  os_id   = 2514 # Windows 2025 Standard x64 - retrieved via `vultr-cli os list`
}

globals "vultr" "reserved_ip" {
  label = global.project
}

generate_hcl "z_ssh_public_key_file.tf" {
  content {
    variable "ssh_public_key_file" {
      type      = string
      sensitive = false
    }

    locals {
      ssh_public_key_file = var.ssh_public_key_file
    }
  }
}

import {
  source = "/modules/vultr/instance.tm.hcl"
}
