stack {
  name = "201 Shared"

  tags = [
    "dev",
    "shared",
    "networking",
  ]

  after = [
    "/stacks/dev/10-cloud-base",
  ]
}

globals {
  allowed_cidrs = ["${global.my_ip}/32"]
}

import {
  source = "/modules/ec2/common_data.tm.hcl"
}

import {
  source = "/modules/ec2/subnet.tm.hcl"
}

import {
  source = "/modules/ec2/security_group.tm.hcl"
}
