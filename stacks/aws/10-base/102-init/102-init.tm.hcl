stack {
  name = "001 Services"

  tags = [
    "aws",
    "base",
    "init",
  ]

  after = [
    "/stacks/aws/10-base/101-empty-project",
  ]
}

import {
  source = "/modules/aws/*/__init__.tm.hcl"
}
