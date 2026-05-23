stack {
  name = "Vultr Instance"

  tags = [
    "instance",
    "services",
    "vultr",
    "vultr-services",
  ]

  after = [
    "/plugins/providers/vultr/stacks/10-shared",
  ]
}

import {
  source = "/plugins/providers/vultr/modules/instance.tm.hcl"
}
