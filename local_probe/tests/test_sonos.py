import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from family_app_probe.sonos import SonosAdapter


class SonosAdapterTests(unittest.TestCase):
    def test_speaker_label_removes_ssdp_network_details(self):
        self.assertEqual(
            SonosAdapter._speaker_label("192.168.128.187 - Sonos Arc - RINCON_38420B4A05F001400"),
            "Sonos Arc",
        )
        self.assertEqual(
            SonosAdapter._speaker_label("192.168.128.188 - Sonos Sub - RINCON_F0F6C1E4ACD001400"),
            "Sonos Sub",
        )

    def test_speaker_label_keeps_a_regular_name(self):
        self.assertEqual(SonosAdapter._speaker_label("Woonkamer rechts"), "Woonkamer rechts")

    def test_local_play_mode_controls_toggle_shuffle_and_repeat(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_player_status", return_value={"shuffle": False, "repeat": False}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "toggle_shuffle", None)
        soap.assert_called_once_with("192.168.1.10", "AVTransport", "SetPlayMode", {"InstanceID": 0, "NewPlayMode": "SHUFFLE_NOREPEAT"})

    def test_local_crossfade_control_uses_av_transport(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_player_status", return_value={"crossfade": False}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "toggle_crossfade", None)
        soap.assert_called_once_with("192.168.1.10", "AVTransport", "SetCrossfadeMode", {"InstanceID": 0, "CrossfadeMode": 1})

    def test_local_audio_and_sleep_controls_use_supported_sonos_services(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "set_bass", "7")
        soap.assert_called_once_with("192.168.1.10", "RenderingControl", "SetBass", {"InstanceID": 0, "DesiredBass": 7})

        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "set_sleep_timer", "30")
        soap.assert_called_once_with("192.168.1.10", "AVTransport", "ConfigureSleepTimer", {"InstanceID": 0, "NewSleepTimerDuration": "00:30:00"})

    def test_local_seek_and_device_settings_use_local_services(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "seek", "95")
        soap.assert_called_once_with("192.168.1.10", "AVTransport", "Seek", {"InstanceID": 0, "Unit": "REL_TIME", "Target": "00:01:35"})

        with patch.object(adapter, "_player_status", return_value={"led_on": True}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "toggle_led", None)
        soap.assert_called_once_with("192.168.1.10", "DeviceProperties", "SetLEDState", {"DesiredLEDState": "Off"})

    def test_optional_output_and_calibration_settings_follow_reported_capabilities(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_extended_player_status", return_value={"can_output_fixed": True, "output_fixed": False}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "toggle_output_fixed", None)
        soap.assert_called_once_with("192.168.1.10", "RenderingControl", "SetOutputFixed", {"InstanceID": 0, "DesiredFixed": 1})

        with patch.object(adapter, "_extended_player_status", return_value={"can_room_calibration_status": True, "room_calibration_enabled": True}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "toggle_room_calibration", None)
        soap.assert_called_once_with("192.168.1.10", "RenderingControl", "SetRoomCalibrationStatus", {"InstanceID": 0, "RoomCalibrationEnabled": 0})

    def test_local_queue_controls_use_av_transport(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "remove_queue_item", "Q:0/5")
        soap.assert_called_once_with("192.168.1.10", "AVTransport", "RemoveTrackFromQueue", {"InstanceID": 0, "ObjectID": "Q:0/5"})

    def test_direct_media_uri_can_play_queue_or_follow_current_track(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "queue_uri", "https://radio.example/stream.mp3")
        soap.assert_called_once_with(
            "192.168.1.10",
            "AVTransport",
            "AddURIToQueue",
            {"InstanceID": 0, "EnqueuedURI": "https://radio.example/stream.mp3", "EnqueuedURIMetaData": "", "DesiredFirstTrackNumberEnqueued": 0, "EnqueueAsNext": 0},
        )

        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "set_next_uri", "x-sonosapi-stream:station")
        soap.assert_called_once_with(
            "192.168.1.10",
            "AVTransport",
            "SetNextAVTransportURI",
            {"InstanceID": 0, "NextURI": "x-sonosapi-stream:station", "NextURIMetaData": ""},
        )

        with self.assertRaisesRegex(RuntimeError, "geldige Sonos-bron"):
            adapter.control("group:coordinator", "play_uri", "file:///private/etc/passwd")

    def test_local_queue_reorder_uses_queue_position(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_extended_player_status", return_value={"queue": [{"id": "Q:0/1"}, {"id": "Q:0/2"}]}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "move_queue_item_up", "Q:0/2")
        soap.assert_called_once_with(
            "192.168.1.10",
            "AVTransport",
            "ReorderTracksInQueue",
            {"InstanceID": 0, "StartingIndex": 2, "NumberOfTracks": 1, "InsertBefore": 1},
        )

    def test_local_alarm_create_uses_alarm_clock(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "create_alarm", '{"time":"07:30","recurrence":"WEEKDAYS"}')
        soap.assert_called_once_with(
            "192.168.1.10",
            "AlarmClock",
            "CreateAlarm",
            {
                "StartLocalTime": "07:30:00",
                "Duration": "00:30:00",
                "Recurrence": "WEEKDAYS",
                "Enabled": 1,
                "RoomUUID": "coordinator",
                "ProgramURI": "x-rincon-buzzer:0",
                "ProgramMetaData": "",
                "PlayMode": "NORMAL",
                "Volume": 20,
                "IncludeLinkedZones": 1,
            },
        )

    def test_local_alarm_toggle_preserves_existing_alarm_settings(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        alarm = {"id": "7", "time": "06:45:00", "duration": "00:20:00", "recurrence": "DAILY", "enabled": True, "room": "coordinator", "program_uri": "x-rincon-buzzer:0", "program_metadata": "", "play_mode": "NORMAL", "volume": "14", "include_linked_zones": "1"}
        with patch.object(adapter, "_extended_player_status", return_value={"alarms": [alarm]}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "toggle_alarm", '{"id":"7"}')
        self.assertEqual(soap.call_args.args[:3], ("192.168.1.10", "AlarmClock", "UpdateAlarm"))
        self.assertEqual(soap.call_args.args[3]["Enabled"], 0)
        self.assertEqual(soap.call_args.args[3]["Volume"], "14")

    def test_local_alarm_update_changes_time_recurrence_and_volume(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        alarm = {"id": "7", "time": "06:45:00", "duration": "00:20:00", "recurrence": "DAILY", "enabled": True, "room": "coordinator", "program_uri": "x-rincon-buzzer:0", "program_metadata": "", "play_mode": "NORMAL", "volume": "14", "include_linked_zones": "1"}
        with patch.object(adapter, "_extended_player_status", return_value={"alarms": [alarm]}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "update_alarm", '{"id":"7","time":"07:15","recurrence":"WEEKENDS","volume":26}')
        self.assertEqual(soap.call_args.args[:3], ("192.168.1.10", "AlarmClock", "UpdateAlarm"))
        self.assertEqual(soap.call_args.args[3]["StartLocalTime"], "07:15:00")
        self.assertEqual(soap.call_args.args[3]["Recurrence"], "WEEKENDS")
        self.assertEqual(soap.call_args.args[3]["Volume"], 26)

    def test_local_alarm_snooze_only_targets_running_alarm(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        alarm = {"id": "7", "time": "06:45:00"}
        with patch.object(adapter, "_extended_player_status", return_value={"alarms": [alarm], "running_alarm_id": "7"}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "snooze_alarm", '{"id":"7"}')
        soap.assert_called_once_with("192.168.1.10", "AVTransport", "SnoozeAlarm", {"InstanceID": 0, "Duration": "00:10:00"})

    def test_local_tv_source_uses_home_theater_stream(self):
        adapter = SonosAdapter()
        adapter.players["RINCON_ARC"] = "192.168.1.10"
        with patch.object(adapter, "_extended_player_status", return_value={"can_tv_input": True}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:RINCON_ARC", "switch_to_tv", None)
        self.assertEqual(soap.call_count, 2)
        self.assertEqual(soap.call_args_list[0].args[:3], ("192.168.1.10", "AVTransport", "SetAVTransportURI"))
        self.assertEqual(soap.call_args_list[0].args[3]["CurrentURI"], "x-sonos-htastream:RINCON_ARC:spdif")
        self.assertEqual(soap.call_args_list[1].args, ("192.168.1.10", "AVTransport", "Play", {"InstanceID": 0, "Speed": 1}))

    def test_local_line_in_controls_use_audio_in_service(self):
        adapter = SonosAdapter()
        adapter.players["linein"] = "192.168.1.10"
        status = {"can_line_in": True, "line_in_icon": "linein"}
        with patch.object(adapter, "_extended_player_status", return_value=status), patch.object(adapter, "_soap") as soap:
            adapter.control("group:linein", "select_line_in", None)
        soap.assert_called_once_with("192.168.1.10", "AudioIn", "SelectAudio", {"ObjectID": "x-rincon-stream:linein"})

        with patch.object(adapter, "_extended_player_status", return_value=status), patch.object(adapter, "_soap") as soap:
            adapter.control("group:linein", "set_line_in_level", "42")
        soap.assert_called_once_with("192.168.1.10", "AudioIn", "SetLineInLevel", {"DesiredLeftLineInLevel": 42, "DesiredRightLineInLevel": 42})

        with patch.object(adapter, "_extended_player_status", return_value=status), patch.object(adapter, "_soap") as soap:
            adapter.control("group:linein", "rename_line_in", "Platenspeler")
        soap.assert_called_once_with("192.168.1.10", "AudioIn", "SetAudioInputAttributes", {"DesiredName": "Platenspeler", "DesiredIcon": "linein"})

    def test_local_playable_favorite_uses_its_bridge_uri(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        favorite = {"id": "FV:2/3", "uri": "x-sonosapi-stream:station", "metadata": "<DIDL-Lite />"}
        with patch.object(adapter, "_extended_player_status", return_value={"favorites": [favorite]}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "load_favorite", "FV:2/3")
        self.assertEqual(soap.call_args_list[0].args[:3], ("192.168.1.10", "AVTransport", "SetAVTransportURI"))
        self.assertEqual(soap.call_args_list[0].args[3]["CurrentURI"], "x-sonosapi-stream:station")
        self.assertEqual(soap.call_args_list[1].args, ("192.168.1.10", "AVTransport", "Play", {"InstanceID": 0, "Speed": 1}))

    def test_local_saved_queue_can_be_saved_and_started(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "save_queue", "Zaterdagavond")
        soap.assert_called_once_with("192.168.1.10", "AVTransport", "SaveQueue", {"InstanceID": 0, "Title": "Zaterdagavond", "ObjectID": ""})

        queue = {"id": "SQ:7", "uri": "file:///jffs/settings/savedqueues.rsq#7", "metadata": "<DIDL-Lite />"}
        with patch.object(adapter, "_extended_player_status", return_value={"saved_queues": [queue]}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "load_saved_queue", "SQ:7")
        self.assertEqual(soap.call_args_list[0].args[:3], ("192.168.1.10", "AVTransport", "SetAVTransportURI"))
        self.assertEqual(soap.call_args_list[1].args, ("192.168.1.10", "AVTransport", "Play", {"InstanceID": 0, "Speed": 1}))

    def test_saved_queue_can_be_deleted_and_library_can_be_refreshed(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_content_directory") as directory:
            adapter.control("group:coordinator", "refresh_music_library", None)
        directory.assert_called_once_with("192.168.1.10", "RefreshShareIndex", {"AlbumArtistDisplayOption": "NONE"})

        queue = {"id": "SQ:7", "uri": "file:///jffs/settings/savedqueues.rsq#7", "metadata": "<DIDL-Lite />"}
        with patch.object(adapter, "_extended_player_status", return_value={"saved_queues": [queue]}), patch.object(adapter, "_content_directory") as directory:
            adapter.control("group:coordinator", "delete_saved_queue", "SQ:7")
        directory.assert_called_once_with("192.168.1.10", "DestroyObject", {"ObjectID": "SQ:7"})

    def test_local_room_name_preserves_existing_zone_configuration(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_extended_player_status", return_value={"can_rename_room": True, "room_configuration": "1"}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "rename_room", "Filmkamer")
        soap.assert_called_once_with(
            "192.168.1.10",
            "DeviceProperties",
            "SetZoneAttributes",
            {"DesiredZoneName": "Filmkamer", "DesiredIcon": "", "DesiredConfiguration": "1"},
        )

    def test_local_tv_autoplay_and_home_theater_feedback_controls(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        status = {"can_tv_autoplay": True, "autoplay_linked_zones": False, "use_autoplay_volume": False}
        with patch.object(adapter, "_extended_player_status", return_value=status), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "toggle_autoplay_linked_zones", None)
        soap.assert_called_once_with("192.168.1.10", "DeviceProperties", "SetAutoplayLinkedZones", {"Source": "spdif", "IncludeLinkedZones": 1})

        with patch.object(adapter, "_extended_player_status", return_value=status), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "set_autoplay_volume", "28")
        soap.assert_called_once_with("192.168.1.10", "DeviceProperties", "SetAutoplayVolume", {"Source": "spdif", "Volume": 28})

        adapter.topology_members["kitchen"] = {"id": "kitchen", "name": "Keuken"}
        with patch.object(adapter, "_extended_player_status", return_value=status), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "set_autoplay_room", "kitchen")
        soap.assert_called_once_with("192.168.1.10", "DeviceProperties", "SetAutoplayRoomUUID", {"Source": "spdif", "RoomUUID": "kitchen"})

        with patch.object(adapter, "_extended_player_status", return_value={"can_home_theater_feedback": True, "ir_repeater_on": True, "led_feedback_on": False}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "toggle_ir_repeater", None)
        soap.assert_called_once_with("192.168.1.10", "HTControl", "SetIRRepeaterState", {"DesiredIRRepeaterState": "Off"})

    def test_local_ir_remote_learning_uses_home_theater_service(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        status = {"can_home_theater_feedback": True}
        with patch.object(adapter, "_extended_player_status", return_value=status), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "identify_ir_remote", "20")
        soap.assert_called_once_with("192.168.1.10", "HTControl", "IdentifyIRRemote", {"Timeout": 20})

        with patch.object(adapter, "_extended_player_status", return_value=status), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "learn_ir_code", '{"code":"VolUp","timeout":30}')
        soap.assert_called_once_with("192.168.1.10", "HTControl", "LearnIRCode", {"IRCode": "VolUp", "Timeout": 30})

        with patch.object(adapter, "_extended_player_status", return_value=status), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "commit_ir_remote", "Tv-afstandsbediening")
        soap.assert_called_once_with("192.168.1.10", "HTControl", "CommitLearnedIRCodes", {"Name": "Tv-afstandsbediening"})

    def test_home_theater_eq_only_sets_supported_values(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        with patch.object(adapter, "_extended_player_status", return_value={"home_theater_eq": {"NightMode": 0, "SurroundLevel": 3}}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "set_home_theater_eq", '{"eq_type":"NightMode","value":"7"}')
        soap.assert_called_once_with("192.168.1.10", "RenderingControl", "SetEQ", {"InstanceID": 0, "EQType": "NightMode", "DesiredValue": 1})

        with patch.object(adapter, "_extended_player_status", return_value={"home_theater_eq": {"NightMode": 0}}):
            with self.assertRaisesRegex(RuntimeError, "niet beschikbaar"):
                adapter.control("group:coordinator", "set_home_theater_eq", '{"eq_type":"SurroundLevel","value":"3"}')

        with patch.object(adapter, "_extended_player_status", return_value={"home_theater_eq": {"HeightChannelLevel": 0}}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "set_home_theater_eq", '{"eq_type":"HeightChannelLevel","value":"42"}')
        soap.assert_called_once_with("192.168.1.10", "RenderingControl", "SetEQ", {"InstanceID": 0, "EQType": "HeightChannelLevel", "DesiredValue": 10})

    def test_local_group_member_removal_requires_explicit_confirmation(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        adapter.group_members["coordinator"] = [
            {"id": "coordinator", "is_coordinator": True},
            {"id": "satellite", "is_coordinator": False},
        ]
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "remove_group_member", '{"member_id":"satellite","confirmed":true}')
        soap.assert_called_once_with("192.168.1.10", "GroupManagement", "RemoveMember", {"MemberID": "satellite"})

        with self.assertRaisesRegex(RuntimeError, "Bevestig eerst"):
            adapter.control("group:coordinator", "remove_group_member", '{"member_id":"satellite","confirmed":false}')

    def test_local_group_member_addition_requires_independent_known_speaker(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        adapter.topology_members["kitchen"] = {"id": "kitchen", "boot_seq": "42", "is_satellite": False}
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "add_group_member", '{"member_id":"kitchen","confirmed":true}')
        soap.assert_called_once_with("192.168.1.10", "GroupManagement", "AddMember", {"MemberID": "kitchen", "BootSeq": "42"})

        adapter.topology_members["surround"] = {"id": "surround", "boot_seq": "43", "is_satellite": True}
        with self.assertRaisesRegex(RuntimeError, "zelfstandige Sonos-speaker"):
            adapter.control("group:coordinator", "add_group_member", '{"member_id":"surround","confirmed":true}')

    def test_local_home_theater_removal_and_room_calibration_use_device_properties(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        adapter.group_members["coordinator"] = [
            {"id": "coordinator", "is_coordinator": True, "calibration_state": "2"},
            {"id": "sub", "is_coordinator": False, "is_satellite": True, "calibration_state": "5"},
        ]
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "remove_group_member", '{"member_id":"sub","confirmed":true}')
        soap.assert_called_once_with("192.168.1.10", "DeviceProperties", "RemoveHTSatellite", {"SatRoomUUID": "sub"})

        response = ElementTree.fromstring("<root><PlayId>42</PlayId></root>")
        with patch.object(adapter, "_soap", return_value=response) as soap:
            adapter.control("group:coordinator", "start_room_calibration", '{"confirmed":true}')
        soap.assert_called_once_with(
            "192.168.1.10",
            "DeviceProperties",
            "RoomDetectionStartChirping",
            {"Channel": 0, "DurationMilliseconds": 3000, "ChirpIfPlayingSwappableAudio": 0},
        )
        self.assertEqual(adapter.room_detection_play_ids["coordinator"], "42")
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "stop_room_calibration", '{"confirmed":true}')
        soap.assert_called_once_with("192.168.1.10", "DeviceProperties", "RoomDetectionStopChirping", {"PlayId": "42"})

    def test_local_home_theater_satellite_addition_uses_confirmed_channel_map(self):
        adapter = SonosAdapter()
        adapter.players["arc"] = "192.168.1.10"
        adapter.group_members["arc"] = [{"id": "arc", "is_coordinator": True, "channel_map": "arc:LF,RF"}]
        adapter.topology_members["sub"] = {"id": "sub", "boot_seq": "33", "is_satellite": False}
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:arc", "add_ht_satellite", '{"member_id":"sub","role":"sub","confirmed":true}')
        soap.assert_called_once_with("192.168.1.10", "DeviceProperties", "AddHTSatellite", {"HTSatChanMapSet": "arc:LF,RF;sub:SW"})

    def test_local_stereo_pair_operations_use_confirmed_channel_maps(self):
        adapter = SonosAdapter()
        adapter.players["left"] = "192.168.1.10"
        adapter.group_members["left"] = [{"id": "left", "is_coordinator": True}]
        adapter.topology_members["right"] = {"id": "right", "boot_seq": "19", "is_satellite": False}
        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:left", "create_stereo_pair", '{"member_id":"right","confirmed":true}')
        soap.assert_called_once_with("192.168.1.10", "DeviceProperties", "CreateStereoPair", {"ChannelMapSet": "left:LF,LF;right:RF,RF"})

        with patch.object(adapter, "_soap") as soap:
            adapter.control("group:left", "separate_stereo_pair", '{"channel_map":"left:LF,LF;right:RF,RF","confirmed":true}')
        soap.assert_called_once_with("192.168.1.10", "DeviceProperties", "SeparateStereoPair", {"ChannelMapSet": "left:LF,LF;right:RF,RF"})

    def test_local_member_volume_control_targets_the_selected_speaker(self):
        adapter = SonosAdapter()
        adapter.players["coordinator"] = "192.168.1.10"
        adapter.member_players["surround"] = "192.168.1.11"
        with patch.object(adapter, "_member_audio_status", return_value={"volume": 18, "muted": False, "fixed": False}), patch.object(adapter, "_soap") as soap:
            adapter.control("group:coordinator", "member_volume_up", "surround")
        soap.assert_called_once_with("192.168.1.11", "RenderingControl", "SetVolume", {"InstanceID": 0, "Channel": "Master", "DesiredVolume": 23})
