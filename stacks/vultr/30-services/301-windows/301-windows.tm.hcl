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
  plan = "vcg-a40-4c-20g-8vram"
}

globals "vultr" "reserved_ip" {
  backups = "disabled"
  label   = global.project
  os_id   = 2516 # Windows Core 2025 Standard x64 - retrieved via `vultr os list`
}

import {
  source = "/modules/vultr/instance.tm.hcl"
}
