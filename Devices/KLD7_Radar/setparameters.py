from kld7 import KLD7, KLD7Exception


def _safe_close(self):
    if getattr(self, "_port", None):
        try:
            self._port.close()
        except Exception:
            pass
    self._port = None

KLD7.close = _safe_close

def send_command(radar, cmd: str, payload: bytes = b''):
    """Send a framed command and return (code, payload) from response."""
    header = cmd.encode('ASCII')
    length = struct.pack('<I', len(payload))
    packet = header + length + payload
    radar._port.write(packet)
    return radar._read_packet()

def set_radar_parameters(port):
    try:
        with KLD7(port) as radar:
            # --- INIT ---
            print("=== INIT sequence ===")
            code, payload = send_command(radar, 'INIT', struct.pack('<I', 0))
            print(f"INIT Response Code: {code}")
            print(f"INIT Payload: {payload}")

            # --- Set parameters ---
            radar.params.DEDI = 2   # Both directions
            radar.params.ANTH = 0   # ±90°
            radar.params.RATH = 0
            radar.params.RRAI = 2
            radar.params.MARA = 100
            radar.params.MIRA = 0
            radar.params.THOF = 30

            print(
                f"DEDI: {radar.params.DEDI}, "
                f"ANTH: {radar.params.ANTH}, "
                f"RATH: {radar.params.RATH}, "
                f"RRAI: {radar.params.RRAI}, "
                f"MARA: {radar.params.MARA}, "
                f"MIRA: {radar.params.MIRA}"
            )

            # --- Verify with GRPS ---
            print("=== GRPS verify ===")
            radar._port.timeout = 5
            try:
                code, payload = send_command(radar, 'GRPS')
                print(f"GRPS Response Code: {code}")
                print(f"GRPS Payload: {payload}")
                for param in dir(radar.params):
                    if not param.startswith('_'):
                        print(f"{param}: {getattr(radar.params, param)}")
            except KLD7Exception as read_error:
                print(f"GRPS read error: {read_error}")

    except KLD7Exception as e:
        print(f"Radar error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

# Monkey‑patch KLD7 to guard None in _drain_serial
def _safe_drain_serial(self):
    if not getattr(self, "_port", None):
        return
    old_timeout = self._port.timeout
    # Original drain logic here if needed
    self._port.timeout = old_timeout

KLD7._drain_serial = _safe_drain_serial

if __name__ == "__main__":
    set_radar_parameters('/dev/ttyUSB0')
