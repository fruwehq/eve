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
  plan    = "vcg-a40-4c-20g-8vram"
  os_id   = 2516 # Windows Core 2025 Standard x64 - retrieved via `vultr-cli os list`
}

globals "vultr" "reserved_ip" {
  label = global.project
}

import {
  source = "/modules/vultr/instance.tm.hcl"
}
