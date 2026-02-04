stack {
  name = "201 Shared"

  tags = [
    "dev",
    "shared",
    "dns",
  ]

  after = [
    "/stacks/dev/10-cloud-base",
  ]
}

import {
  source = "/modules/ec2/elastic_ip.tm.hcl"
}
