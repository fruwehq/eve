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
  source = "/modules/gcp/compute/firewall.tm.hcl"
}
