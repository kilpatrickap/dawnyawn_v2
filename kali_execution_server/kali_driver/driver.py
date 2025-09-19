# kali_execution_server/kali_driver/driver.py
import os
import time
import docker
import paramiko


# This file is now self-contained and does not import from itself or other project files.

class KaliContainer:
    def __init__(self, owner):
        self._owner = owner
        self._ssh_client = None

        print("  [+] Creating Kali container from 'dawnyawn-kali-agent' image...")
        self._container = owner._docker_client.containers.create(
            image="dawnyawn-kali-agent",
            command="/usr/sbin/sshd -D",
            ports={"22/tcp": None},
            detach=True
        )
        self._ensure_started()
        print(f"  [+] Container '{self._container.short_id}' created and running.")

    def _ensure_started(self):
        self._container.reload()
        if self._container.status != "running":
            self._container.start()
            time.sleep(2)
        self._container.reload()

    def _ensure_connected(self):
        if self._ssh_client and self._ssh_client.get_transport().is_active():
            return

        self._container.reload()
        port_data = self._container.ports.get('22/tcp')
        if not port_data or 'HostPort' not in port_data[0]:
            raise Exception(f"Failed to find mapped SSH port for container {self._container.id}")

        public_port = int(port_data[0]['HostPort'])
        key_path = os.path.expanduser('~/.ssh/id_ecdsa')
        if not os.path.exists(key_path):
            raise FileNotFoundError(f"SSH private key not found at {key_path}.")

        self._ssh_client = paramiko.SSHClient()
        self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._ssh_client.connect(
            hostname='localhost', port=public_port, username='root',
            key_filename=key_path, timeout=30
        )

    def send_command_and_get_output(self, command: str) -> str:
        self._ensure_connected()
        print(f"  [+] Sending command: '{command}'")
        stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=1800)
        output = stdout.read().decode('utf-8', errors='ignore').strip()
        error_output = stderr.read().decode('utf-8', errors='ignore').strip()
        if error_output:
            output += "\n--- STDERR ---\n" + error_output
        if not output:
            print("\n--- ⚠️ EXECUTION WARNING: EMPTY RESULT ---")
        return output

    def destroy(self):
        if self._ssh_client:
            self._ssh_client.close()
        try:
            self._container.reload()
            print(f"\n  [+] Cleaning up container '{self._container.short_id}'...")
            if self._container.status in ["running", "created"]:
                self._container.stop()
            self._container.remove(force=True)
            print("  [+] Cleanup complete.")
        except docker.errors.NotFound:
            pass


class KaliManager:
    def __init__(self):
        try:
            self._docker_client = docker.from_env()
            self._docker_client.ping()
        except Exception as e:
            print("FATAL ERROR: Could not connect to Docker. Is it running?")
            raise e

    def create_container(self) -> "KaliContainer":  # Use string hint for self-reference
        return KaliContainer(owner=self)