stack {
  name = "102 Base"

  tags = [
    "vultr",
    "base",
    "late-init",
  ]

  after = [
    "/stacks/vultr/10-base/102-init",
  ]
}

import {
  source = "/modules/vultr/__late_init__.tm.hcl"
}
