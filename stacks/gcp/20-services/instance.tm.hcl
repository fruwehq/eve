stack {
  name = "GCP Instance"

  tags = [
    "gcp",
    "gcp-services",
    "instance",
    "services",
  ]

  after = [
    "/stacks/gcp/10-shared",
  ]
}

import {
  source = "/modules/gcp/compute/instance.tm.hcl"
}
