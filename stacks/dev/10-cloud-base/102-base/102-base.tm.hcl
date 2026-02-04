stack {
  name = "102 Base"

  tags = [
    "dev",
    "cloud-base",
    "base",
  ]

  after = [
    "/stacks/dev/00-bootstrap",
  ]
}

import {
  source = "/modules/*/__base__.tm.hcl"
}
