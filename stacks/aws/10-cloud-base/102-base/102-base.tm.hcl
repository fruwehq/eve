stack {
  name = "102 Base"

  tags = [
    "aws",
    "cloud-base",
    "base",
  ]

  after = [
    "/stacks/aws/00-bootstrap",
  ]
}

import {
  source = "/modules/*/__base__.tm.hcl"
}
