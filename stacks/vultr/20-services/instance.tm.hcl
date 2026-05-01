stack {
  name = "Vultr Instance"

  tags = [
    "instance",
    "services",
    "vultr",
    "vultr-services",
  ]

  after = [
    "/stacks/vultr/10-shared",
  ]
}

import {
  source = "/modules/vultr/instance.tm.hcl"
}
