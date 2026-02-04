stack {
  name = "101 Services"

  tags = [
    "dev",
    "cloud-base",
    "base",
    "services",
  ]

  after = [
    "/stacks/dev/00-bootstrap",
  ]
}

import {
  source = "/modules/*/__init__.tm.hcl"
}
