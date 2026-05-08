stack {
  name = "GCP Instance"

  tags = [
    "gcp",
    "gcp-services",
    "instance",
    "services",
  ]

  after = [
    "/plugins/providers/gcp/stacks/10-shared",
  ]
}

import {
  source = "/plugins/providers/gcp/modules/compute/instance.tm.hcl"
}
