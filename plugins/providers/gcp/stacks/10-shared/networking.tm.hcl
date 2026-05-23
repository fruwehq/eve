stack {
  name = "GCP Networking"

  tags = [
    "gcp",
    "gcp-shared",
    "networking",
    "shared",
  ]
}

import {
  source = "/plugins/providers/gcp/modules/compute/firewall.tm.hcl"
}
