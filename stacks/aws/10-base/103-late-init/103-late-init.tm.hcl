stack {
  name = "102 Base"

  tags = [
    "aws",
    "base",
    "late-init",
  ]

  after = [
    "/stacks/aws/10-base/102-init",
  ]
}

import {
  source = "/modules/aws/*/__late_init__.tm.hcl"
}
