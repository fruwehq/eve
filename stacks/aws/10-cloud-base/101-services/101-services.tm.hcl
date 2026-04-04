stack {
  name = "101 Services"

  tags = [
    "aws",
    "cloud-base",
    "base",
    "services",
  ]

  after = [
    "/stacks/aws/00-bootstrap",
  ]
}

import {
  source = "/modules/*/__init__.tm.hcl"
}
