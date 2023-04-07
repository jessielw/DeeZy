xml_audio_base_atmos = """<?xml version="1.0"?>
<job_config>
  <input>
    <audio>
      <atmos_mezz version="1">
        <file_name>-</file_name>
        <timecode_frame_rate>-</timecode_frame_rate>    <!-- One of: not_indicated, 23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60 -->
        <offset>auto</offset>
        <ffoa>auto</ffoa>
        <storage>
          <local>
            <path>-</path>    <!-- string -->
          </local>
        </storage>
      </atmos_mezz>
    </audio>
  </input>
  <filter>
    <audio>
      <encode_to_atmos_ddp version="1">
        <loudness>
          <measure_only>
            <metering_mode>1770-4</metering_mode>    <!-- One of: 1770-4, 1770-3, 1770-2, 1770-1, LeqA -->
            <dialogue_intelligence>false</dialogue_intelligence>    <!-- boolean: true or false -->
            <speech_threshold>80</speech_threshold>    <!-- integer: from 0 to 100 -->
          </measure_only>
        </loudness>
        <data_rate>-</data_rate>    <!-- One or multiple of: 384, 448, 576, 640, 768, 1024 -->
        <timecode_frame_rate>[FRAMERATE]</timecode_frame_rate>    <!-- One of: not_indicated, 23.976, 24, 25, 29.97, 30, 48, 50, 59.94, 60 -->
        <start>first_frame_of_action</start>    <!-- string -->
        <end>end_of_file</end>    <!-- string -->
        <time_base>file_position</time_base>    <!-- One of: file_position, embedded_timecode -->
        <prepend_silence_duration>0.0</prepend_silence_duration>    <!-- string -->
        <append_silence_duration>0.0</append_silence_duration>    <!-- string -->
        <drc>
          <line_mode_drc_profile>film_light</line_mode_drc_profile>    <!-- One of: film_standard, film_light, music_standard, music_light, speech, none -->
          <rf_mode_drc_profile>film_light</rf_mode_drc_profile>    <!-- One of: film_standard, film_light, music_standard, music_light, speech, none -->
        </drc>
        <downmix>
          <loro_center_mix_level>0</loro_center_mix_level>    <!-- One of: +3, +1.5, 0, -1.5, -3, -4.5, -6, -inf -->
          <loro_surround_mix_level>-1.5</loro_surround_mix_level>    <!-- One of: -1.5, -3, -4.5, -6, -inf -->
          <ltrt_center_mix_level>0</ltrt_center_mix_level>    <!-- One of: +3, +1.5, 0, -1.5, -3, -4.5, -6, -inf -->
          <ltrt_surround_mix_level>-1.5</ltrt_surround_mix_level>    <!-- One of: -1.5, -3, -4.5, -6, -inf -->
          <preferred_downmix_mode>loro</preferred_downmix_mode>    <!-- One of: loro, ltrt, ltrt-pl2, not_indicated -->
        </downmix>
        <custom_trims>
          <surround_trim_5_1>0</surround_trim_5_1>    <!-- One of: 0, -3, -6, -9, auto -->
          <height_trim_5_1>-3</height_trim_5_1>    <!-- One of: -3, -6, -9, -12, auto -->
        </custom_trims>
      </encode_to_atmos_ddp>
    </audio>
  </filter>
  <output>
    <ec3 version="1">
      <file_name>-</file_name>    <!-- string -->
      <storage>
        <local>
          <path>-</path>    <!-- string -->
        </local>
      </storage>
    </ec3>
  </output>
  <misc>
    <temp_dir>
      <clean_temp>true</clean_temp>
      <path>-</path>
    </temp_dir>
  </misc>
</job_config>"""
