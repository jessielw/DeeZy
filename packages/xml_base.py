xml_audio_base_ddp = """<?xml version="1.0"?>
<job_config>
  <input>
    <audio>
      <wav version="1">
        <file_name>-</file_name>
        <timecode_frame_rate>not_indicated</timecode_frame_rate>
        <offset>auto</offset>
        <ffoa>auto</ffoa>
        <storage>
          <local>
            <path>-</path>
          </local>
        </storage>
      </wav>
    </audio>
  </input>
  <filter>
    <audio>
      <pcm_to_ddp version="3">
        <loudness>
          <measure_only>
            <metering_mode>1770-3</metering_mode>
            <dialogue_intelligence>true</dialogue_intelligence>
            <speech_threshold>20</speech_threshold>
          </measure_only>
        </loudness>
        <encoder_mode>-</encoder_mode>
        <bitstream_mode>complete_main</bitstream_mode>
        <downmix_config>off</downmix_config>
        <data_rate>-</data_rate>
        <timecode_frame_rate>not_indicated</timecode_frame_rate>
        <start>first_frame_of_action</start>
        <end>end_of_file</end>
        <time_base>file_position</time_base>
        <prepend_silence_duration>0.0</prepend_silence_duration>
        <append_silence_duration>0.0</append_silence_duration> 
        <lfe_on>true</lfe_on>
        <dolby_surround_mode>not_indicated</dolby_surround_mode>
        <dolby_surround_ex_mode>no</dolby_surround_ex_mode>
        <user_data>-1</user_data>
        <drc>
          <line_mode_drc_profile>music_light</line_mode_drc_profile>
          <rf_mode_drc_profile>music_light</rf_mode_drc_profile>
        </drc>
        <lfe_lowpass_filter>true</lfe_lowpass_filter>
        <surround_90_degree_phase_shift>true</surround_90_degree_phase_shift>
        <surround_3db_attenuation>true</surround_3db_attenuation>
        <downmix>
          <loro_center_mix_level>-3</loro_center_mix_level>
          <loro_surround_mix_level>-3</loro_surround_mix_level>
          <ltrt_center_mix_level>-3</ltrt_center_mix_level>
          <ltrt_surround_mix_level>-3</ltrt_surround_mix_level>
          <preferred_downmix_mode>-</preferred_downmix_mode>
        </downmix>
        <allow_hybrid_downmix>false</allow_hybrid_downmix>
        <embedded_timecodes>
          <starting_timecode>off</starting_timecode>
          <frame_rate>auto</frame_rate>
        </embedded_timecodes>
      </pcm_to_ddp>
    </audio>
  </filter>
  <output>
    <ac3 version="1">
      <file_name>-</file_name>
      <storage>
        <local>
          <path>-</path>
        </local>
      </storage>
    </ac3>
  </output>
  <misc>
    <temp_dir>
      <clean_temp>true</clean_temp>
      <path>-</path>
    </temp_dir>
  </misc>
</job_config>"""
