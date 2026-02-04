stack {
  name = "301 Windows"

  tags = [
    "dev",
    "services",
    "windows",
  ]

  after = [
    "/stacks/dev/20-shared",
  ]
}

globals {
  instance_type  = "g5.2xlarge"
  use_spot       = true
}

import {
  source = "/modules/ec2/instance.tm.hcl"
}

import {
  source = "/modules/ec2/spot_instance.tm.hcl"
}
