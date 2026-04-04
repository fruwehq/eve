stack {
  name = "201 Shared"

  tags = [
    "aws",
    "shared",
    "networking",
  ]

  after = [
    "/stacks/aws/10-cloud-base",
  ]
}

globals {
  allowed_cidrs = ["${global.my_ip}/32"]
}

import {
  source = "/modules/ec2/vpc.tm.hcl"
}

import {
  source = "/modules/ec2/security_group.tm.hcl"
}
