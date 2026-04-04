stack {
  name = "201 Shared"

  tags = [
    "vultr",
    "shared",
    "networking",
  ]

  after = [
    "/stacks/vultr/10-base",
  ]
}

globals "vultr" "reserved_ip" {
  label = global.project
}

import {
  source = "/modules/vultr/reserved_ip.tm.hcl"
}
