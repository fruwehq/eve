stack {
  name = "001 Services"

  tags = [
    "vultr",
    "base",
    "init",
  ]

  after = [
    "/stacks/vultr/10-base/101-empty-project",
  ]
}

import {
  source = "/modules/vultr/__init__.tm.hcl"
}
