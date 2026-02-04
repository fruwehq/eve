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
}

import {
  source = "/modules/windows/ec2.tm.hcl"
}
