stack {
  name = "TrueNAS Instance"

  tags = [
    "instance",
    "services",
    "truenas",
    "truenas-services",
  ]

  after = [
    "/plugins/providers/truenas/stacks/truenas/10-shared",
  ]
}

import {
  source = "/plugins/providers/truenas/modules/truenas/vm.tm.hcl"
}
