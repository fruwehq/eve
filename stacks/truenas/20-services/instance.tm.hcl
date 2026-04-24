stack {
  name = "TrueNAS Instance"

  tags = [
    "instance",
    "services",
    "truenas",
    "truenas-services",
  ]

  after = [
    "/stacks/truenas/10-shared",
  ]
}

import {
  source = "/modules/truenas/vm.tm.hcl"
}
