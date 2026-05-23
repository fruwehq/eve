# frozen_string_literal: true

require "fileutils"

module Eve
  module SDK
    module Workdir
      def self.root
        @root ||= File.expand_path("../..", File.dirname(__FILE__))
      end

      def self.root=(path)
        @root = path
      end

      def self.workdir_base
        base = ENV["EVE_INSTANCE_WORKDIR"]
        base && !base.empty? ? File.expand_path(base) : File.join(root, ".generated/instances")
      end

      def self.state_base
        base = ENV["EVE_STATE_DIR"]
        return File.expand_path(base) if base && !base.empty?

        File.join(root, ".eve/state")
      end

      def self.instance_workdir(instance_name)
        File.join(workdir_base, instance_name)
      end

      def self.state_path(instance_name)
        File.join(state_base, "instances", "#{instance_name}.json")
      end

      def self.overlay_path(instance_name)
        File.join(instance_workdir(instance_name), "catalog.local.yaml")
      end

      def self.tf_workdir(instance_name)
        File.join(instance_workdir(instance_name), "tf")
      end

      def self.tf_state_base(instance_name)
        File.join(tf_workdir(instance_name), "state")
      end

      def self.tf_data_base(instance_name)
        File.join(tf_workdir(instance_name), "data")
      end

      def self.tf_data_dir(instance_name)
        File.join(tf_data_base(instance_name), "default")
      end

      def self.logs_dir(instance_name)
        File.join(instance_workdir(instance_name), "logs")
      end

      def self.uploads_dir(instance_name)
        File.join(instance_workdir(instance_name), "uploads")
      end

      def self.ensure_dir(path)
        FileUtils.mkdir_p(path)
        path
      end

      def self.all_paths(instance_name)
        {
          "INSTANCE_NAME" => instance_name,
          "INSTANCE_WORKDIR" => instance_workdir(instance_name),
          "INSTANCE_OVERLAY_PATH" => overlay_path(instance_name),
          "INSTANCE_STATE_PATH" => state_path(instance_name),
          "INSTANCE_TF_WORKDIR" => tf_workdir(instance_name),
          "INSTANCE_TF_STATE_BASE" => tf_state_base(instance_name),
          "INSTANCE_TF_DATA_BASE" => tf_data_base(instance_name),
          "INSTANCE_TF_DATA_DIR" => tf_data_dir(instance_name)
        }
      end
    end
  end
end
