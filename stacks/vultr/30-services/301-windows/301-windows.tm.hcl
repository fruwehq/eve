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
  # plan = "vcg-a40-1c-5g-2vram"   # 1 vCPU, 5 GB RAM, 90 GB NVMe, 3 TB/mo, $0.075/hr, 1/24 NVIDIA A40 (2 GB VRAM)
  plan = "vcg-a40-2c-10g-4vram"    # 2 vCPUs, 10 GB RAM, 180 GB NVMe, 4 TB/mo, $0.144/hr, 1/12 NVIDIA A40 (4 GB VRAM)
  # plan = "vcg-a40-4c-20g-8vram"  # 4 vCPUs, 20 GB RAM, 360 GB NVMe, 5 TB/mo, $0.288/hr, 1/6 NVIDIA A40 (8 GB VRAM)
  # plan = "vcg-a40-6c-30g-12vram" # 6 vCPUs, 30 GB RAM, 550 GB NVMe, 6 TB/mo, $0.432/hr, 1/4 NVIDIA A40 (12 GB VRAM)
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
