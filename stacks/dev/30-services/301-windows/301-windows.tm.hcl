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
  availability_zone = "ap-northeast-1b"
  instance_type  = "g5.2xlarge"
  use_spot       = false
}

import {
  source = "/modules/ec2/instance.tm.hcl"
}
