# frozen_string_literal: true

require "fileutils"

module Eve
  module SDK
    # Workdir is the single source of truth for Eve's local data paths.
    #
    # By default, Eve keeps runtime state under the repository root:
    #   <repo>/.eve/
    #   <repo>/.generated/
    #
    # When EVE_HOME is set, that directory becomes the data root instead:
    #   <EVE_HOME>/.eve/
    #   <EVE_HOME>/.generated/
    #
    # Source-tree paths still use repo_root. Callers that need instance
    # registries, state files, generated overlays, plugins, config, or secrets
    # should use the methods below instead of constructing .eve/.generated paths.
    module Workdir
      def self.repo_root
        @repo_root ||= File.expand_path("../..", File.dirname(__FILE__))
      end

      def self.repo_root=(path)
        @repo_root = File.expand_path(path)
      end

      def self.root
        return @root_override if @root_override

        home = ENV["EVE_HOME"]
        home && !home.empty? ? File.expand_path(home) : repo_root
      end

      def self.root=(path)
        @root_override = File.expand_path(path)
      end

      def self.eve_dir
        File.join(root, ".eve")
      end

      def self.generated_dir
        File.join(root, ".generated")
      end

      def self.config_path
        path_from_env("EVE_CONFIG_PATH", File.join(eve_dir, "config.yaml"))
      end

      def self.instance_registry_path
        path_from_env("EVE_INSTANCE_REGISTRY", File.join(eve_dir, "instances.yaml"))
      end

      def self.plugin_sources_path
        File.join(eve_dir, "plugin-sources.yaml")
      end

      def self.plugins_dir
        File.join(eve_dir, "plugins")
      end

      def self.workdir_base
        path_from_env("EVE_INSTANCE_WORKDIR", File.join(generated_dir, "instances"))
      end

      def self.state_base
        path_from_env("EVE_STATE_DIR", File.join(eve_dir, "state"))
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

      def self.path_from_env(name, default_path)
        value = ENV[name]
        value && !value.empty? ? File.expand_path(value, Dir.pwd) : default_path
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
