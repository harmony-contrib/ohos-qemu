#!/usr/bin/env python3
"""Exact post-391 AudioOnset35 explicit clock variant source component.
This is product source wiring only. It cannot grant any runtime/onset claim.
"""
from pathlib import Path
import argparse,fcntl,hashlib,importlib.util,json,os,stat,subprocess,sys,tempfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PATCH_ROOT=HERE.parents[4]
MANIFEST_SHA256='1c7a01a320e18f42ceecc049f14e28deee2c710be6996f3747bc3faa9e7b6b0d'
FILES={'drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_render.c': {'after': {'bytes': 36379,
                                                                                       'sha256': '0cb97d7662f2d67e222e8e852b269af146c3e3c14476efe7b75d5820856845a5'},
                                                                             'before': {'bytes': 35754,
                                                                                        'sha256': '84df61e94415a48ebfd08837bec4e6849b548615233f1aecd3501391e316be7b'}},
 'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain.h': {'after': {'bytes': 6317,
                                                                                                                'sha256': 'e3a42cc5f7ffc4132e15f6f93f3dd25c4f520aa779126724f5064f539b004783'},
                                                                                                      'before': {'bytes': 6173,
                                                                                                                 'sha256': '9aaa77714aea71fac0e0a679102c045ceb82feffb9eea0fc70d3bccd8210f203'}},
 'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain_manager.h': {'after': {'bytes': 18852,
                                                                                                                        'sha256': 'ae359f66d16f8173442a5042a6fdfc150aa790dd908fb7df0d38957e39fc91aa'},
                                                                                                              'before': {'bytes': 18818,
                                                                                                                         'sha256': 'e47ed09cb5acc62fba59fd05bd265daa5acc1ec6ca80cea3acd8ec1b20d20345'}},
 'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain.cpp': {'after': {'bytes': 33805,
                                                                                                              'sha256': '8f65d51f593ece9cd66c980739df1503d8ec0f45e3473654ff90e7ea160696ad'},
                                                                                                    'before': {'bytes': 33420,
                                                                                                               'sha256': '307aeccab22a083bab8ecd98fd69328aa3cfb0ff6a1d6c8f40d6e5ccfb5e97be'}},
 'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain_manager.cpp': {'after': {'bytes': 142357,
                                                                                                                      'sha256': '15e92d3ffa070ff49558810b32f0e5b995f0d730154c1eb4b5c7c777dce4a120'},
                                                                                                            'before': {'bytes': 142179,
                                                                                                                       'sha256': '097cc47d402d1f0197a43382a26a884231a75f1c8651256ba97b3cfb9739cfe7'}},
 'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.cpp': {'after': {'bytes': 10852,
                                                                                                      'sha256': '3287eae2c813263646483c6b89c46824899bd7aa8482cddce039916a5259648d'},
                                                                                            'before': {'bytes': 9221,
                                                                                                       'sha256': 'b9c6525a27860986284faf5dbbc885ab1baa204bb45d70dea8b3fc59481fe52a'}},
 'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.h': {'after': {'bytes': 8181,
                                                                                                    'sha256': '9d642679ffeedc3537d175c3b723229e98e756272f91367e13380c04e5352cda'},
                                                                                          'before': {'bytes': 7934,
                                                                                                     'sha256': 'ceabe85cf50f0971e9f31056f0a861014badc0d29b0567b862607ed3d6127fbd'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_audio_format_converter_node.h': {'after': {'bytes': 5368,
                                                                                                                           'sha256': '3c750daec6b0d5bcf70862cf3b9806345645d7eae4805106b084a27be3e2ed9f'},
                                                                                                                 'before': {'bytes': 5282,
                                                                                                                            'sha256': '6add879044a09fbe6f32457e9db2739d9a9bac68e52443178c062f2d39659d5c'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_output_node.h': {'after': {'bytes': 5282,
                                                                                                                'sha256': '0c993e036d1ed67145bb062ee36741d3bd774dac2766492bf48b24d26ad50b9b'},
                                                                                                      'before': {'bytes': 5207,
                                                                                                                 'sha256': '0cb13d69586da3a2de9fd478ede91b3d441b79cd275842fb80aa0bc377b3490c'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_audio_format_converter_node.cpp': {'after': {'bytes': 49098,
                                                                                                                         'sha256': 'dd8392339e5304b4e1cd5cdfba9ab4ff153348f8b9ecf4613e1f5e0545a58dbc'},
                                                                                                               'before': {'bytes': 48163,
                                                                                                                          'sha256': '9403b4080b81ff628129de99badd8739bace3092814241f6658ee03f5e542849'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_limiter_node.cpp': {'after': {'bytes': 4213,
                                                                                                          'sha256': '3c63df48f7fb61d16b230e4ee7b518e94dda148504f1cc42787172a942807180'},
                                                                                                'before': {'bytes': 4139,
                                                                                                           'sha256': 'cf95e2272498c63abda290a61a28dcb509ffcc2ad0a00fc559d65d827a5888f9'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_loudness_gain_node.cpp': {'after': {'bytes': 14216,
                                                                                                                'sha256': '2c0d60be0a84dbdd39d6f0776e8ce3d917e004eed60d3f7e98df13a9676a55c8'},
                                                                                                      'before': {'bytes': 14098,
                                                                                                                 'sha256': 'dffdc31ae1b76a1e9eadde979586bbab0bd41ca504ae2257d875b8c7e39f5798'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_mixer_node.cpp': {'after': {'bytes': 10054,
                                                                                                        'sha256': '5dc437b02f293b37431bf2d8e74eb3a63c320da562dcec87d65ca08e60f4f32d'},
                                                                                              'before': {'bytes': 9978,
                                                                                                         'sha256': '9deaf68aa028933d8d94ed506894e977e7b7b1a1a1e1182b9f61afff3eb7d9d9'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_render_effect_node.cpp': {'after': {'bytes': 40492,
                                                                                                                'sha256': 'e5c7d7e360ddd6b148f762508f962429fa3a75f3ed2a821d50775eb355353969'},
                                                                                                      'before': {'bytes': 40207,
                                                                                                                 'sha256': '06aef094db3e03506da6bd2a8ff4967f8644ae5c34b9a473f517e9bcbbf1c2e6'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_session_effect_node.cpp': {'after': {'bytes': 39582,
                                                                                                                 'sha256': '74903bd7f18e6b611d3d1588fc20fcd0a2252e050df9028a92c987cfe867a1d3'},
                                                                                                       'before': {'bytes': 39406,
                                                                                                                  'sha256': '0baf66f2c46002a687b37c722908a90a37861c152afdf84f0c401ad54c490b8e'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_input_node.cpp': {'after': {'bytes': 16790,
                                                                                                             'sha256': '405e54e82099d5d59d8715f89f2791f39c6e048035cd552701d26d51fec2f4eb'},
                                                                                                   'before': {'bytes': 16557,
                                                                                                              'sha256': 'a41efee416c218ba7eb59aa2a274086200343b582e4a112bac7152b483cc71ea'}},
 'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp': {'after': {'bytes': 33634,
                                                                                                              'sha256': '05cbf92d1687ca9f0218876bb459a7a04e842eb4df6567de2c934f2741297de1'},
                                                                                                    'before': {'bytes': 32685,
                                                                                                               'sha256': 'f745b31951504e60acbbf5fb8286d7f8b9a8f6c77112114cc773972f5913cab9'}},
 'foundation/multimedia/audio_framework/services/audio_service/BUILD.gn': {'after': {'bytes': 33848,
                                                                                     'sha256': 'fe04e5d164b39218310440a1233d6c80b57fbbf62285d64c08f7d9a67aa98aca'},
                                                                           'before': {'bytes': 33811,
                                                                                      'sha256': 'efdb97383dce2334ca9b110171d949d49ba34ac97144e24fba77a7d6808f7454'}},
 'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579.h': {'after': {'bytes': 3233,
                                                                                                            'sha256': '459629d5037fa3756ede76e937310c344c3847ad3344fd376175d7afb520bc0e'},
                                                                                                  'before': None},
 'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579_wire.h': {'after': {'bytes': 471,
                                                                                                                 'sha256': '869150565cf1a62cfd01d2a6d86380baa5209fb534d7a3208ed2b3c47d164967'},
                                                                                                       'before': None},
 'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset580_wire.h': {'after': {'bytes': 862,
                                                                                                                 'sha256': 'c5e500563cbfc36a66e027ff8f8ca234d8053cc61607778a660348a4d8bba1a4'},
                                                                                                       'before': None},
 'foundation/multimedia/audio_framework/services/audio_service/common/include/limiter/audio_limiter.h': {'after': {'bytes': 2914,
                                                                                                                   'sha256': '87423077ba759159e3fc868271088b30569c2d3efee0ce510568398246f1bd01'},
                                                                                                         'before': {'bytes': 2718,
                                                                                                                    'sha256': 'b16524c356bc7ec958d540464b2581964452863ae601156675f88b8ab2c9a787'}},
 'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_clock_domain.h': {'after': {'bytes': 10375,
                                                                                                                   'sha256': 'd905aabdbbc46ed8e7fb16492626a52327126de7c8088f29867d6ac5cf05fe36'},
                                                                                                         'before': None},
 'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_kernel_clock_review.h': {'after': {'bytes': 793,
                                                                                                                          'sha256': '122ac852dff2761b88c1bce8e18767572f7ca2eb3d9ce47f844bfe1ca749b739'},
                                                                                                                'before': None},
 'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579.cpp': {'after': {'bytes': 17443,
                                                                                                          'sha256': 'b0f8aefb4e3fd49c83f331ed2a8a35cb1bfec701ab76f814e3c8b269899b1ca0'},
                                                                                                'before': None},
 'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579_global.inc': {'after': {'bytes': 18325,
                                                                                                                 'sha256': '0883aab0922cd944d1965dfd3611e7410dfdfaba006154b5c99f65e45fd9c938'},
                                                                                                       'before': None},
 'foundation/multimedia/audio_framework/services/audio_service/common/src/limiter/audio_limiter.cpp': {'after': {'bytes': 16006,
                                                                                                                 'sha256': 'a5ebbdd29028279a5dd410be743cbc9970d6b2a23c9f6698b545432a52543665'},
                                                                                                       'before': {'bytes': 14931,
                                                                                                                  'sha256': '5df04013f0d2d9b49b3f9918f1490ce947371a745f796e10d513e123b0fc2313'}},
 'foundation/multimedia/audio_framework/services/audio_service/server/include/renderer_in_server.h': {'after': {'bytes': 18099,
                                                                                                                'sha256': '66b4d0a29cf86c244da18ceb6255321a46c1dcc0b4ff5a60554cf63aedf0e0bb'},
                                                                                                      'before': {'bytes': 18063,
                                                                                                                 'sha256': '5211f48b1d12bebfb06bed00ffb6947f0a18b0129a5db5fc3591976358704a5f'}},
 'foundation/multimedia/audio_framework/services/audio_service/server/src/renderer_in_server.cpp': {'after': {'bytes': 157370,
                                                                                                              'sha256': '745d7430d3c031d78dfa92d57ada3f7299bef8e769131494af4bc0fb74230f0a'},
                                                                                                    'before': {'bytes': 156379,
                                                                                                               'sha256': '7baf8439c6632196c378c956db6851d654954b597612b6762e6a7f48f29dd1ad'}},
 'third_party/alsa-lib/src/pcm/media398_onset.h': {'after': {'bytes': 35874,
                                                             'sha256': 'e87750fe8121194992d48dd991e7f93fb27c0de6d8b76f8d7b115968881e44ac'},
                                                   'before': {'bytes': 33433,
                                                              'sha256': '7dd8cf8102dda20a9211e9d56e79416626fcaf5c8ddc449ace5bd37fcc9438d2'}},
 'third_party/alsa-lib/src/pcm/media598_onset.h': {'after': {'bytes': 35685,
                                                             'sha256': '132c8f95e8f4422642359a2b2cb4d4dedf25b15c67b701b90795fd5be0a1bffa'},
                                                   'before': None},
 'third_party/alsa-lib/src/pcm/media598_wire.h': {'after': {'bytes': 1050,
                                                            'sha256': '8d6957da5dbce30a31ed4aedb5224e4a51e0d25de73564bcbc70871e36899dc3'},
                                                  'before': None},
 'third_party/alsa-lib/src/pcm/onset579_clock_domain.h': {'after': {'bytes': 10375,
                                                                    'sha256': 'd905aabdbbc46ed8e7fb16492626a52327126de7c8088f29867d6ac5cf05fe36'},
                                                          'before': None},
 'third_party/alsa-lib/src/pcm/onset579_kernel_clock_review.h': {'after': {'bytes': 793,
                                                                           'sha256': '122ac852dff2761b88c1bce8e18767572f7ca2eb3d9ce47f844bfe1ca749b739'},
                                                                 'before': None},
 'third_party/alsa-lib/src/pcm/pcm_hw.c': {'after': {'bytes': 61797,
                                                     'sha256': '04629c6ddf430fe129bc783d150eb3a716b2b0957b73e79dc135711aa89a9366'},
                                           'before': {'bytes': 61029,
                                                      'sha256': 'd6dfc03c36ec0d78414c39047e43e55d81f3d0497361235aea40c977ea949f71'}}}
HEADS={'drivers/peripheral': '69094b77aa2200160207b1b06b3c0b586ae2157c',
 'foundation/multimedia/audio_framework': '6932fa64335b8272ca4a59de7808ab0d6c9eae7a',
 'third_party/alsa-lib': 'dececa15b19fba7445fbdb5559b60e88f53f6960'}
PREVIOUS_EPOCHS={'canonical63ed': {'drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_render.c': {'bytes': 36379,
                                                                                               'sha256': '0cb97d7662f2d67e222e8e852b269af146c3e3c14476efe7b75d5820856845a5'},
                   'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain.h': {'bytes': 6317,
                                                                                                                        'sha256': 'e3a42cc5f7ffc4132e15f6f93f3dd25c4f520aa779126724f5064f539b004783'},
                   'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain_manager.h': {'bytes': 18852,
                                                                                                                                'sha256': 'ae359f66d16f8173442a5042a6fdfc150aa790dd908fb7df0d38957e39fc91aa'},
                   'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain.cpp': {'bytes': 33805,
                                                                                                                      'sha256': '8f65d51f593ece9cd66c980739df1503d8ec0f45e3473654ff90e7ea160696ad'},
                   'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain_manager.cpp': {'bytes': 142357,
                                                                                                                              'sha256': '15e92d3ffa070ff49558810b32f0e5b995f0d730154c1eb4b5c7c777dce4a120'},
                   'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.cpp': {'bytes': 10852,
                                                                                                              'sha256': '3287eae2c813263646483c6b89c46824899bd7aa8482cddce039916a5259648d'},
                   'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.h': {'bytes': 8181,
                                                                                                            'sha256': '9d642679ffeedc3537d175c3b723229e98e756272f91367e13380c04e5352cda'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_audio_format_converter_node.h': {'bytes': 5368,
                                                                                                                                   'sha256': '3c750daec6b0d5bcf70862cf3b9806345645d7eae4805106b084a27be3e2ed9f'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_output_node.h': {'bytes': 5282,
                                                                                                                        'sha256': '0c993e036d1ed67145bb062ee36741d3bd774dac2766492bf48b24d26ad50b9b'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_audio_format_converter_node.cpp': {'bytes': 49098,
                                                                                                                                 'sha256': 'dd8392339e5304b4e1cd5cdfba9ab4ff153348f8b9ecf4613e1f5e0545a58dbc'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_limiter_node.cpp': {'bytes': 4213,
                                                                                                                  'sha256': '3c63df48f7fb61d16b230e4ee7b518e94dda148504f1cc42787172a942807180'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_loudness_gain_node.cpp': {'bytes': 14216,
                                                                                                                        'sha256': '2c0d60be0a84dbdd39d6f0776e8ce3d917e004eed60d3f7e98df13a9676a55c8'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_mixer_node.cpp': {'bytes': 10054,
                                                                                                                'sha256': '5dc437b02f293b37431bf2d8e74eb3a63c320da562dcec87d65ca08e60f4f32d'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_render_effect_node.cpp': {'bytes': 40492,
                                                                                                                        'sha256': 'e5c7d7e360ddd6b148f762508f962429fa3a75f3ed2a821d50775eb355353969'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_session_effect_node.cpp': {'bytes': 39582,
                                                                                                                         'sha256': '74903bd7f18e6b611d3d1588fc20fcd0a2252e050df9028a92c987cfe867a1d3'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_input_node.cpp': {'bytes': 16790,
                                                                                                                     'sha256': '405e54e82099d5d59d8715f89f2791f39c6e048035cd552701d26d51fec2f4eb'},
                   'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp': {'bytes': 33634,
                                                                                                                      'sha256': '05cbf92d1687ca9f0218876bb459a7a04e842eb4df6567de2c934f2741297de1'},
                   'foundation/multimedia/audio_framework/services/audio_service/BUILD.gn': {'bytes': 33848,
                                                                                             'sha256': 'fe04e5d164b39218310440a1233d6c80b57fbbf62285d64c08f7d9a67aa98aca'},
                   'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579.h': {'bytes': 3233,
                                                                                                                    'sha256': '459629d5037fa3756ede76e937310c344c3847ad3344fd376175d7afb520bc0e'},
                   'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579_wire.h': {'bytes': 471,
                                                                                                                         'sha256': '869150565cf1a62cfd01d2a6d86380baa5209fb534d7a3208ed2b3c47d164967'},
                   'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset580_wire.h': {'bytes': 862,
                                                                                                                         'sha256': 'c5e500563cbfc36a66e027ff8f8ca234d8053cc61607778a660348a4d8bba1a4'},
                   'foundation/multimedia/audio_framework/services/audio_service/common/include/limiter/audio_limiter.h': {'bytes': 2914,
                                                                                                                           'sha256': '87423077ba759159e3fc868271088b30569c2d3efee0ce510568398246f1bd01'},
                   'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_clock_domain.h': {'bytes': 10375,
                                                                                                                           'sha256': 'd905aabdbbc46ed8e7fb16492626a52327126de7c8088f29867d6ac5cf05fe36'},
                   'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_kernel_clock_review.h': {'bytes': 731,
                                                                                                                                  'sha256': 'f235c3ca52dcd75ccef830b79f7f9d07ee09379f672cd2832185f9decaa3a82c'},
                   'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579.cpp': {'bytes': 17443,
                                                                                                                  'sha256': 'b0f8aefb4e3fd49c83f331ed2a8a35cb1bfec701ab76f814e3c8b269899b1ca0'},
                   'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579_global.inc': {'bytes': 18325,
                                                                                                                         'sha256': '0883aab0922cd944d1965dfd3611e7410dfdfaba006154b5c99f65e45fd9c938'},
                   'foundation/multimedia/audio_framework/services/audio_service/common/src/limiter/audio_limiter.cpp': {'bytes': 16006,
                                                                                                                         'sha256': 'a5ebbdd29028279a5dd410be743cbc9970d6b2a23c9f6698b545432a52543665'},
                   'foundation/multimedia/audio_framework/services/audio_service/server/include/renderer_in_server.h': {'bytes': 18099,
                                                                                                                        'sha256': '66b4d0a29cf86c244da18ceb6255321a46c1dcc0b4ff5a60554cf63aedf0e0bb'},
                   'foundation/multimedia/audio_framework/services/audio_service/server/src/renderer_in_server.cpp': {'bytes': 157370,
                                                                                                                      'sha256': '745d7430d3c031d78dfa92d57ada3f7299bef8e769131494af4bc0fb74230f0a'},
                   'third_party/alsa-lib/src/pcm/media398_onset.h': {'bytes': 35874,
                                                                     'sha256': 'e87750fe8121194992d48dd991e7f93fb27c0de6d8b76f8d7b115968881e44ac'},
                   'third_party/alsa-lib/src/pcm/media598_onset.h': {'bytes': 35685,
                                                                     'sha256': '132c8f95e8f4422642359a2b2cb4d4dedf25b15c67b701b90795fd5be0a1bffa'},
                   'third_party/alsa-lib/src/pcm/media598_wire.h': {'bytes': 1050,
                                                                    'sha256': '8d6957da5dbce30a31ed4aedb5224e4a51e0d25de73564bcbc70871e36899dc3'},
                   'third_party/alsa-lib/src/pcm/onset579_clock_domain.h': {'bytes': 10375,
                                                                            'sha256': 'd905aabdbbc46ed8e7fb16492626a52327126de7c8088f29867d6ac5cf05fe36'},
                   'third_party/alsa-lib/src/pcm/onset579_kernel_clock_review.h': {'bytes': 731,
                                                                                   'sha256': 'f235c3ca52dcd75ccef830b79f7f9d07ee09379f672cd2832185f9decaa3a82c'},
                   'third_party/alsa-lib/src/pcm/pcm_hw.c': {'bytes': 61797,
                                                             'sha256': '04629c6ddf430fe129bc783d150eb3a716b2b0957b73e79dc135711aa89a9366'}},
 'corrected391': {'drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_render.c': {'bytes': 36379,
                                                                                              'sha256': '0cb97d7662f2d67e222e8e852b269af146c3e3c14476efe7b75d5820856845a5'},
                  'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain.h': {'bytes': 6317,
                                                                                                                       'sha256': 'e3a42cc5f7ffc4132e15f6f93f3dd25c4f520aa779126724f5064f539b004783'},
                  'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain_manager.h': {'bytes': 18852,
                                                                                                                               'sha256': 'ae359f66d16f8173442a5042a6fdfc150aa790dd908fb7df0d38957e39fc91aa'},
                  'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain.cpp': {'bytes': 33805,
                                                                                                                     'sha256': '8f65d51f593ece9cd66c980739df1503d8ec0f45e3473654ff90e7ea160696ad'},
                  'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain_manager.cpp': {'bytes': 142357,
                                                                                                                             'sha256': '15e92d3ffa070ff49558810b32f0e5b995f0d730154c1eb4b5c7c777dce4a120'},
                  'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.cpp': {'bytes': 10852,
                                                                                                             'sha256': '3287eae2c813263646483c6b89c46824899bd7aa8482cddce039916a5259648d'},
                  'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.h': {'bytes': 8181,
                                                                                                           'sha256': '9d642679ffeedc3537d175c3b723229e98e756272f91367e13380c04e5352cda'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_audio_format_converter_node.h': {'bytes': 5368,
                                                                                                                                  'sha256': '3c750daec6b0d5bcf70862cf3b9806345645d7eae4805106b084a27be3e2ed9f'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_output_node.h': {'bytes': 5282,
                                                                                                                       'sha256': '0c993e036d1ed67145bb062ee36741d3bd774dac2766492bf48b24d26ad50b9b'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_audio_format_converter_node.cpp': {'bytes': 49098,
                                                                                                                                'sha256': 'dd8392339e5304b4e1cd5cdfba9ab4ff153348f8b9ecf4613e1f5e0545a58dbc'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_limiter_node.cpp': {'bytes': 4213,
                                                                                                                 'sha256': '3c63df48f7fb61d16b230e4ee7b518e94dda148504f1cc42787172a942807180'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_loudness_gain_node.cpp': {'bytes': 14216,
                                                                                                                       'sha256': '2c0d60be0a84dbdd39d6f0776e8ce3d917e004eed60d3f7e98df13a9676a55c8'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_mixer_node.cpp': {'bytes': 10054,
                                                                                                               'sha256': '5dc437b02f293b37431bf2d8e74eb3a63c320da562dcec87d65ca08e60f4f32d'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_render_effect_node.cpp': {'bytes': 40492,
                                                                                                                       'sha256': 'e5c7d7e360ddd6b148f762508f962429fa3a75f3ed2a821d50775eb355353969'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_session_effect_node.cpp': {'bytes': 39582,
                                                                                                                        'sha256': '74903bd7f18e6b611d3d1588fc20fcd0a2252e050df9028a92c987cfe867a1d3'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_input_node.cpp': {'bytes': 16790,
                                                                                                                    'sha256': '405e54e82099d5d59d8715f89f2791f39c6e048035cd552701d26d51fec2f4eb'},
                  'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp': {'bytes': 33634,
                                                                                                                     'sha256': '05cbf92d1687ca9f0218876bb459a7a04e842eb4df6567de2c934f2741297de1'},
                  'foundation/multimedia/audio_framework/services/audio_service/BUILD.gn': {'bytes': 33848,
                                                                                            'sha256': 'fe04e5d164b39218310440a1233d6c80b57fbbf62285d64c08f7d9a67aa98aca'},
                  'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579.h': {'bytes': 3233,
                                                                                                                   'sha256': '459629d5037fa3756ede76e937310c344c3847ad3344fd376175d7afb520bc0e'},
                  'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579_wire.h': {'bytes': 471,
                                                                                                                        'sha256': '869150565cf1a62cfd01d2a6d86380baa5209fb534d7a3208ed2b3c47d164967'},
                  'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset580_wire.h': None,
                  'foundation/multimedia/audio_framework/services/audio_service/common/include/limiter/audio_limiter.h': {'bytes': 2914,
                                                                                                                          'sha256': '87423077ba759159e3fc868271088b30569c2d3efee0ce510568398246f1bd01'},
                  'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_clock_domain.h': None,
                  'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_kernel_clock_review.h': None,
                  'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579.cpp': {'bytes': 17347,
                                                                                                                 'sha256': 'cbe3c4836264c9769e82ae9f6c548fb1495313c0d695892f5ee7b3e99450235d'},
                  'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579_global.inc': None,
                  'foundation/multimedia/audio_framework/services/audio_service/common/src/limiter/audio_limiter.cpp': {'bytes': 16006,
                                                                                                                        'sha256': 'a5ebbdd29028279a5dd410be743cbc9970d6b2a23c9f6698b545432a52543665'},
                  'foundation/multimedia/audio_framework/services/audio_service/server/include/renderer_in_server.h': {'bytes': 18099,
                                                                                                                       'sha256': '66b4d0a29cf86c244da18ceb6255321a46c1dcc0b4ff5a60554cf63aedf0e0bb'},
                  'foundation/multimedia/audio_framework/services/audio_service/server/src/renderer_in_server.cpp': {'bytes': 157370,
                                                                                                                     'sha256': '745d7430d3c031d78dfa92d57ada3f7299bef8e769131494af4bc0fb74230f0a'},
                  'third_party/alsa-lib/src/pcm/media398_onset.h': {'bytes': 35787,
                                                                    'sha256': 'e17c36c587e8513942922066c74ca31ec8a365c69e26fe4cbce14f0a73efca3d'},
                  'third_party/alsa-lib/src/pcm/media598_onset.h': None,
                  'third_party/alsa-lib/src/pcm/media598_wire.h': None,
                  'third_party/alsa-lib/src/pcm/onset579_clock_domain.h': None,
                  'third_party/alsa-lib/src/pcm/onset579_kernel_clock_review.h': None,
                  'third_party/alsa-lib/src/pcm/pcm_hw.c': {'bytes': 61797,
                                                            'sha256': '04629c6ddf430fe129bc783d150eb3a716b2b0957b73e79dc135711aa89a9366'}},
 'legacy72': {'drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_render.c': {'bytes': 36379,
                                                                                          'sha256': '0cb97d7662f2d67e222e8e852b269af146c3e3c14476efe7b75d5820856845a5'},
              'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain.h': {'bytes': 6317,
                                                                                                                   'sha256': 'e3a42cc5f7ffc4132e15f6f93f3dd25c4f520aa779126724f5064f539b004783'},
              'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain_manager.h': {'bytes': 18852,
                                                                                                                           'sha256': 'ae359f66d16f8173442a5042a6fdfc150aa790dd908fb7df0d38957e39fc91aa'},
              'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain.cpp': {'bytes': 33805,
                                                                                                                 'sha256': '8f65d51f593ece9cd66c980739df1503d8ec0f45e3473654ff90e7ea160696ad'},
              'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain_manager.cpp': {'bytes': 142357,
                                                                                                                         'sha256': '15e92d3ffa070ff49558810b32f0e5b995f0d730154c1eb4b5c7c777dce4a120'},
              'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.cpp': {'bytes': 10852,
                                                                                                         'sha256': '3287eae2c813263646483c6b89c46824899bd7aa8482cddce039916a5259648d'},
              'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.h': {'bytes': 8181,
                                                                                                       'sha256': '9d642679ffeedc3537d175c3b723229e98e756272f91367e13380c04e5352cda'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_audio_format_converter_node.h': {'bytes': 5368,
                                                                                                                              'sha256': '3c750daec6b0d5bcf70862cf3b9806345645d7eae4805106b084a27be3e2ed9f'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_output_node.h': {'bytes': 5282,
                                                                                                                   'sha256': '0c993e036d1ed67145bb062ee36741d3bd774dac2766492bf48b24d26ad50b9b'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_audio_format_converter_node.cpp': {'bytes': 49098,
                                                                                                                            'sha256': 'dd8392339e5304b4e1cd5cdfba9ab4ff153348f8b9ecf4613e1f5e0545a58dbc'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_limiter_node.cpp': {'bytes': 4213,
                                                                                                             'sha256': '3c63df48f7fb61d16b230e4ee7b518e94dda148504f1cc42787172a942807180'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_loudness_gain_node.cpp': {'bytes': 14216,
                                                                                                                   'sha256': '2c0d60be0a84dbdd39d6f0776e8ce3d917e004eed60d3f7e98df13a9676a55c8'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_mixer_node.cpp': {'bytes': 10054,
                                                                                                           'sha256': '5dc437b02f293b37431bf2d8e74eb3a63c320da562dcec87d65ca08e60f4f32d'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_render_effect_node.cpp': {'bytes': 40492,
                                                                                                                   'sha256': 'e5c7d7e360ddd6b148f762508f962429fa3a75f3ed2a821d50775eb355353969'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_session_effect_node.cpp': {'bytes': 39582,
                                                                                                                    'sha256': '74903bd7f18e6b611d3d1588fc20fcd0a2252e050df9028a92c987cfe867a1d3'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_input_node.cpp': {'bytes': 16790,
                                                                                                                'sha256': '405e54e82099d5d59d8715f89f2791f39c6e048035cd552701d26d51fec2f4eb'},
              'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp': {'bytes': 33634,
                                                                                                                 'sha256': '05cbf92d1687ca9f0218876bb459a7a04e842eb4df6567de2c934f2741297de1'},
              'foundation/multimedia/audio_framework/services/audio_service/BUILD.gn': {'bytes': 33848,
                                                                                        'sha256': 'fe04e5d164b39218310440a1233d6c80b57fbbf62285d64c08f7d9a67aa98aca'},
              'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579.h': {'bytes': 3233,
                                                                                                               'sha256': '459629d5037fa3756ede76e937310c344c3847ad3344fd376175d7afb520bc0e'},
              'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579_wire.h': {'bytes': 471,
                                                                                                                    'sha256': '869150565cf1a62cfd01d2a6d86380baa5209fb534d7a3208ed2b3c47d164967'},
              'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset580_wire.h': None,
              'foundation/multimedia/audio_framework/services/audio_service/common/include/limiter/audio_limiter.h': {'bytes': 2914,
                                                                                                                      'sha256': '87423077ba759159e3fc868271088b30569c2d3efee0ce510568398246f1bd01'},
              'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_clock_domain.h': None,
              'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_kernel_clock_review.h': None,
              'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579.cpp': {'bytes': 17305,
                                                                                                             'sha256': '01156918b0a32bed09e987305df72f478a7a1ee19bf471cb4d4cc6f9e6ffdb31'},
              'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579_global.inc': None,
              'foundation/multimedia/audio_framework/services/audio_service/common/src/limiter/audio_limiter.cpp': {'bytes': 16006,
                                                                                                                    'sha256': 'a5ebbdd29028279a5dd410be743cbc9970d6b2a23c9f6698b545432a52543665'},
              'foundation/multimedia/audio_framework/services/audio_service/server/include/renderer_in_server.h': {'bytes': 18099,
                                                                                                                   'sha256': '66b4d0a29cf86c244da18ceb6255321a46c1dcc0b4ff5a60554cf63aedf0e0bb'},
              'foundation/multimedia/audio_framework/services/audio_service/server/src/renderer_in_server.cpp': {'bytes': 157370,
                                                                                                                 'sha256': '745d7430d3c031d78dfa92d57ada3f7299bef8e769131494af4bc0fb74230f0a'},
              'third_party/alsa-lib/src/pcm/media398_onset.h': {'bytes': 35787,
                                                                'sha256': 'e17c36c587e8513942922066c74ca31ec8a365c69e26fe4cbce14f0a73efca3d'},
              'third_party/alsa-lib/src/pcm/media598_onset.h': None,
              'third_party/alsa-lib/src/pcm/media598_wire.h': None,
              'third_party/alsa-lib/src/pcm/onset579_clock_domain.h': None,
              'third_party/alsa-lib/src/pcm/onset579_kernel_clock_review.h': None,
              'third_party/alsa-lib/src/pcm/pcm_hw.c': {'bytes': 61797,
                                                        'sha256': '04629c6ddf430fe129bc783d150eb3a716b2b0957b73e79dc135711aa89a9366'}}}
MIGRATION={'epochs': {'canonical63ed': {'patch': '0004-upgrade-canonical63ed-clock-review.patch',
                              'patch_sha256': '94ddc7474cef950a9ba5da282bac721f1a9f10feeb5f1332372abf8a050bd771'},
            'corrected391': {'patch': '0003-upgrade-corrected391-to-global579.patch',
                             'patch_sha256': 'b35b76132cc915ea07277cdb1665af2483effc48b70bb602a609874e36c73cab'},
            'legacy72': {'patch': '0002-upgrade-legacy72-to-global579.patch',
                         'patch_sha256': '5a5152388f8daf2d9d07c235f617df547cdc6f1571d4633f1a2146940d502df2'}},
 'fresh_noop': 'complete original-before35 tuple only',
 'managed': ['foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset580_wire.h',
             'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_clock_domain.h',
             'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_kernel_clock_review.h',
             'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579.cpp',
             'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579_global.inc',
             'third_party/alsa-lib/src/pcm/media398_onset.h',
             'third_party/alsa-lib/src/pcm/media598_onset.h',
             'third_party/alsa-lib/src/pcm/media598_wire.h',
             'third_party/alsa-lib/src/pcm/onset579_clock_domain.h',
             'third_party/alsa-lib/src/pcm/onset579_kernel_clock_review.h'],
 'managed_by_epoch': {'canonical63ed': ['foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_kernel_clock_review.h',
                                        'third_party/alsa-lib/src/pcm/onset579_kernel_clock_review.h'],
                      'corrected391': ['foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset580_wire.h',
                                       'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_clock_domain.h',
                                       'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_kernel_clock_review.h',
                                       'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579.cpp',
                                       'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579_global.inc',
                                       'third_party/alsa-lib/src/pcm/media398_onset.h',
                                       'third_party/alsa-lib/src/pcm/media598_onset.h',
                                       'third_party/alsa-lib/src/pcm/media598_wire.h',
                                       'third_party/alsa-lib/src/pcm/onset579_clock_domain.h',
                                       'third_party/alsa-lib/src/pcm/onset579_kernel_clock_review.h'],
                      'legacy72': ['foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset580_wire.h',
                                   'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_clock_domain.h',
                                   'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_kernel_clock_review.h',
                                   'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579.cpp',
                                   'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579_global.inc',
                                   'third_party/alsa-lib/src/pcm/media398_onset.h',
                                   'third_party/alsa-lib/src/pcm/media598_onset.h',
                                   'third_party/alsa-lib/src/pcm/media598_wire.h',
                                   'third_party/alsa-lib/src/pcm/onset579_clock_domain.h',
                                   'third_party/alsa-lib/src/pcm/onset579_kernel_clock_review.h']},
 'other_epoch': 'defer_to_original_normal_hooks_NOT_verified; no source writes; every original hook and '
                'strict final gate remains mandatory',
 'readonly_by_epoch': {'canonical63ed': ['drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_render.c',
                                         'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain.h',
                                         'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain_manager.h',
                                         'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain.cpp',
                                         'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain_manager.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.h',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_audio_format_converter_node.h',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_output_node.h',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_audio_format_converter_node.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_limiter_node.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_loudness_gain_node.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_mixer_node.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_render_effect_node.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_session_effect_node.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_input_node.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_service/BUILD.gn',
                                         'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579.h',
                                         'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579_wire.h',
                                         'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset580_wire.h',
                                         'foundation/multimedia/audio_framework/services/audio_service/common/include/limiter/audio_limiter.h',
                                         'foundation/multimedia/audio_framework/services/audio_service/common/include/onset579_clock_domain.h',
                                         'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_onset579_global.inc',
                                         'foundation/multimedia/audio_framework/services/audio_service/common/src/limiter/audio_limiter.cpp',
                                         'foundation/multimedia/audio_framework/services/audio_service/server/include/renderer_in_server.h',
                                         'foundation/multimedia/audio_framework/services/audio_service/server/src/renderer_in_server.cpp',
                                         'third_party/alsa-lib/src/pcm/media398_onset.h',
                                         'third_party/alsa-lib/src/pcm/media598_onset.h',
                                         'third_party/alsa-lib/src/pcm/media598_wire.h',
                                         'third_party/alsa-lib/src/pcm/onset579_clock_domain.h',
                                         'third_party/alsa-lib/src/pcm/pcm_hw.c'],
                       'corrected391': ['drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_render.c',
                                        'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain.h',
                                        'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain_manager.h',
                                        'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain.cpp',
                                        'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain_manager.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.h',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_audio_format_converter_node.h',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_output_node.h',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_audio_format_converter_node.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_limiter_node.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_loudness_gain_node.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_mixer_node.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_render_effect_node.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_session_effect_node.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_input_node.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_service/BUILD.gn',
                                        'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579.h',
                                        'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579_wire.h',
                                        'foundation/multimedia/audio_framework/services/audio_service/common/include/limiter/audio_limiter.h',
                                        'foundation/multimedia/audio_framework/services/audio_service/common/src/limiter/audio_limiter.cpp',
                                        'foundation/multimedia/audio_framework/services/audio_service/server/include/renderer_in_server.h',
                                        'foundation/multimedia/audio_framework/services/audio_service/server/src/renderer_in_server.cpp',
                                        'third_party/alsa-lib/src/pcm/pcm_hw.c'],
                       'legacy72': ['drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_render.c',
                                    'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain.h',
                                    'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain_manager.h',
                                    'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain.cpp',
                                    'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain_manager.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.h',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_audio_format_converter_node.h',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_output_node.h',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_audio_format_converter_node.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_limiter_node.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_loudness_gain_node.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_mixer_node.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_render_effect_node.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_session_effect_node.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_input_node.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_service/BUILD.gn',
                                    'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579.h',
                                    'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579_wire.h',
                                    'foundation/multimedia/audio_framework/services/audio_service/common/include/limiter/audio_limiter.h',
                                    'foundation/multimedia/audio_framework/services/audio_service/common/src/limiter/audio_limiter.cpp',
                                    'foundation/multimedia/audio_framework/services/audio_service/server/include/renderer_in_server.h',
                                    'foundation/multimedia/audio_framework/services/audio_service/server/src/renderer_in_server.cpp',
                                    'third_party/alsa-lib/src/pcm/pcm_hw.c']},
 'readonly_unchanged': ['drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_render.c',
                        'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain.h',
                        'foundation/multimedia/audio_framework/frameworks/native/audioeffect/include/audio_effect_chain_manager.h',
                        'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain.cpp',
                        'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain_manager.cpp',
                        'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.cpp',
                        'foundation/multimedia/audio_framework/services/audio_engine/buffer/hpae_pcm_buffer.h',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_audio_format_converter_node.h',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_output_node.h',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_audio_format_converter_node.cpp',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_limiter_node.cpp',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_loudness_gain_node.cpp',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_mixer_node.cpp',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_render_effect_node.cpp',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_session_effect_node.cpp',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_input_node.cpp',
                        'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp',
                        'foundation/multimedia/audio_framework/services/audio_service/BUILD.gn',
                        'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579.h',
                        'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_onset579_wire.h',
                        'foundation/multimedia/audio_framework/services/audio_service/common/include/limiter/audio_limiter.h',
                        'foundation/multimedia/audio_framework/services/audio_service/common/src/limiter/audio_limiter.cpp',
                        'foundation/multimedia/audio_framework/services/audio_service/server/include/renderer_in_server.h',
                        'foundation/multimedia/audio_framework/services/audio_service/server/src/renderer_in_server.cpp',
                        'third_party/alsa-lib/src/pcm/pcm_hw.c'],
 'schema': 'audio-onset579-exact-known-epoch-clock-review-upgrade/v3'}
LEGACY={'accepted': {'apply': 'apply.sh',
              'path': 'common/drivers/peripheral/audio/accepted_write',
              'paths': ['device/qemu/common/virt_full/audio_alsa/vendor_render.c',
                        'drivers/peripheral/audio/hdi_service/primary_impl/BUILD.gn',
                        'drivers/peripheral/audio/hdi_service/primary_impl/include/audio_internal.h',
                        'drivers/peripheral/audio/hdi_service/primary_impl/src/audio_render.c',
                        'drivers/peripheral/audio/hdi_service/supportlibs/BUILD.gn',
                        'drivers/peripheral/audio/supportlibs/alsa_adapter/include/alsa_lib_render.h',
                        'drivers/peripheral/audio/supportlibs/alsa_adapter/include/alsa_snd_render.h',
                        'drivers/peripheral/audio/supportlibs/alsa_adapter/include/alsa_soundcard.h',
                        'drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_lib_render.c',
                        'drivers/peripheral/audio/supportlibs/alsa_adapter/src/alsa_snd_render.c',
                        'drivers/peripheral/audio/supportlibs/alsa_adapter/src/vendor_render.c',
                        'drivers/peripheral/audio/supportlibs/interfaces/include/audio_if_lib_common.h',
                        'drivers/peripheral/audio/supportlibs/interfaces/include/audio_if_lib_render.h'],
              'script_sha256': {'apply.py': 'c66884bd56eeb75f59b6a236d2f6713ba903389971a31ec1b6a1376ff4b4b100',
                                'apply.sh': 'e9d74057c303b13d388011560450e4f86383d29be8765523f08f5e4b123f6217'},
              'verify': 'apply.py',
              'verify_args': ['--preflight', '--require-patched']},
 'alsa': {'apply': 'apply.sh',
          'path': 'common/third_party/alsa-lib/pcm_onset',
          'paths': ['third_party/alsa-lib/BUILD.gn',
                    'third_party/alsa-lib/src/pcm/media398_onset.h',
                    'third_party/alsa-lib/src/pcm/media398_wire.h',
                    'third_party/alsa-lib/src/pcm/pcm_hw.c',
                    'third_party/alsa-lib/src/pcm/pcm_local.h'],
          'script_sha256': {'apply.py': '07c36a0c0e5d1bedaee219f9107e29e1daa9dc6072419218d743fcaa73734ff4',
                            'apply.sh': 'e9d74057c303b13d388011560450e4f86383d29be8765523f08f5e4b123f6217'},
          'verify': 'apply.py',
          'verify_args': ['--require-patched']},
 'resampler': {'apply': 'apply.sh',
               'path': 'common/foundation/multimedia/audio_framework/audio_resampler_counts',
               'paths': ['foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_audio_format_converter_node.h',
                         'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_audio_format_converter_node.cpp',
                         'foundation/multimedia/audio_framework/services/audio_engine/plugin/resample/include/audio_proresampler.h',
                         'foundation/multimedia/audio_framework/services/audio_engine/plugin/resample/include/audio_proresampler_process.h',
                         'foundation/multimedia/audio_framework/services/audio_engine/plugin/resample/include/resampler.h',
                         'foundation/multimedia/audio_framework/services/audio_engine/plugin/resample/proresampler/audio_proresampler.cpp',
                         'foundation/multimedia/audio_framework/services/audio_engine/plugin/resample/proresampler/audio_proresampler_process.c'],
               'script_sha256': {'apply.py': '46bf180665631c51ff0cbe70931a77c95d787e127745f3c8f608ca56a4266aa5',
                                 'apply.sh': '53ae7fcb0a08f9514ed804cb4b35d89443522ffd33795889000332f15845d454'},
               'verify': 'apply.py',
               'verify_args': ['--preflight', '--require-patched']},
 'sync': {'apply': 'apply.sh',
          'path': 'common/foundation/multimedia/audio_framework/audio_haptic_sync_id',
          'paths': ['foundation/multimedia/audio_framework/config.gni',
                    'foundation/multimedia/audio_framework/frameworks/native/audioutils/BUILD.gn',
                    'foundation/multimedia/audio_framework/frameworks/native/audioutils/include/audio_speed.h',
                    'foundation/multimedia/audio_framework/frameworks/native/audioutils/src/audio_speed.cpp',
                    'foundation/multimedia/audio_framework/interfaces/inner_api/native/audiocommon/include/ring_buffer_wrapper.h',
                    'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_input_node.h',
                    'foundation/multimedia/audio_framework/services/audio_engine/node/include/hpae_sink_output_node.h',
                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_input_node.cpp',
                    'foundation/multimedia/audio_framework/services/audio_engine/node/src/hpae_sink_output_node.cpp',
                    'foundation/multimedia/audio_framework/services/audio_service/BUILD.gn',
                    'foundation/multimedia/audio_framework/services/audio_service/client/include/renderer_in_client.h',
                    'foundation/multimedia/audio_framework/services/audio_service/client/include/renderer_in_client_private.h',
                    'foundation/multimedia/audio_framework/services/audio_service/client/src/renderer_in_client.cpp',
                    'foundation/multimedia/audio_framework/services/audio_service/client/src/renderer_in_client_public.cpp',
                    'foundation/multimedia/audio_framework/services/audio_service/common/include/audio_pitch_processor.h',
                    'foundation/multimedia/audio_framework/services/audio_service/common/include/oh_audio_buffer.h',
                    'foundation/multimedia/audio_framework/services/audio_service/common/src/audio_pitch_processor.cpp',
                    'foundation/multimedia/audio_framework/services/audio_service/common/src/oh_audio_buffer.cpp',
                    'foundation/multimedia/audio_framework/services/audio_service/common/src/oh_audio_buffer_base.cpp',
                    'foundation/multimedia/audio_framework/services/audio_service/server/include/hpae_renderer_stream_impl.h',
                    'foundation/multimedia/audio_framework/services/audio_service/server/include/i_stream.h',
                    'foundation/multimedia/audio_framework/services/audio_service/server/include/i_stream_manager.h',
                    'foundation/multimedia/audio_framework/services/audio_service/server/include/renderer_in_server.h',
                    'foundation/multimedia/audio_framework/services/audio_service/server/src/hpae_adapter_manager.cpp',
                    'foundation/multimedia/audio_framework/services/audio_service/server/src/hpae_renderer_stream_impl.cpp',
                    'foundation/multimedia/audio_framework/services/audio_service/server/src/i_stream_manager.cpp',
                    'foundation/multimedia/audio_framework/services/audio_service/server/src/renderer_in_server.cpp',
                    'third_party/sonic/sonic.c',
                    'third_party/sonic/sonic.h'],
          'script_sha256': {'apply.sh': 'df3430be7357cc7f210c743daf50f9e5e1373eb4ea24a89f3a0b1aa44afa16f0',
                            'verify_source.py': '74706fd0244ca88e275758cdd229270a67d66e79285c478b4f7ef8dd8739449d'},
          'verify': 'verify_source.py',
          'verify_args': ['--require-patched']}}
IMPLEMENTATION={'actual_export': {'bytes': 268160,
                   'path': '/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r68-readonly-sdk-kernel-provider-source579-01/SOURCE.json',
                   'sha256': 'd7528b1571ba956eecc4305b8a480b0f3275c12353c3b06997d306c8df1a8ef3'},
 'files': {'kernel/linux/linux-6.6/arch/arm/Kconfig': {'bytes': 60795,
                                                       'sha256': '4793a64bb6fd5fcae3bf18cfa2a1bc733cee6773379c7aea3985f9f631201e1c'},
           'kernel/linux/linux-6.6/arch/arm/vdso/vgettimeofday.c': {'bytes': 929,
                                                                    'sha256': 'e5bf23424a0c328bea5bc4027f174b8339fb0f5787e7fa8a395d2a571203b513'},
           'kernel/linux/linux-6.6/fs/proc/namespaces.c': {'bytes': 4323,
                                                           'sha256': 'cc38b0cd358741199f25ecb99487caf46e3794bc8d444dd777791b7c1d49fb45'},
           'kernel/linux/linux-6.6/include/linux/time_namespace.h': {'bytes': 4068,
                                                                     'sha256': 'd99650e247b1d4faa704161063a1d7a94e8f9ab56cd28baff2cb4d1095cde81f'},
           'kernel/linux/linux-6.6/init/Kconfig': {'bytes': 67024,
                                                   'sha256': '545e3c8fcb6f44dda9f0c91d1dd1705c6b652578646f824745731a0cd2d07e31'},
           'kernel/linux/linux-6.6/kernel/time/posix-timers.c': {'bytes': 42908,
                                                                 'sha256': '6918cac7acc14895b03d371b0371b9e25ec5b8239aa11fd0d184acc6d2a97955'},
           'kernel/linux/linux-6.6/kernel/time/timekeeping.c': {'bytes': 72851,
                                                                'sha256': 'd56f6561a288a4e8d87162e81038f82008f0168adbd3d6714b02e154f5074e08'},
           'kernel/linux/linux-6.6/lib/vdso/Kconfig': {'bytes': 674,
                                                       'sha256': 'cbf9681abf0e9e41c7ae414cfc7afab0446236e6a09377ca8ced849190e47135'},
           'kernel/linux/linux-6.6/lib/vdso/gettimeofday.c': {'bytes': 10760,
                                                              'sha256': '63881cbf52d1f5d9cb3f5a699720202fac6081827b8b446e138a94dcfa430481'}},
 'generated_config_proven': False,
 'head': '14c77f1541a53e814d89ad6dea5f7f211f9895a6',
 'held_boot_proven': False,
 'package_kernel_correspondence_proven': False,
 'project': 'kernel/linux/linux-6.6',
 'runtime_pass': False,
 'schema': 'audio579-fixed-clock-implementation-review/v1',
 'source_implementation_review_only': True}
IMPLEMENTATION_MANIFEST_SHA256='67f6565084be76e213ed367de61522ad34e440f298513641f5b256c37a736653'
def need(ok,message):
    if not ok:raise ValueError(message)
def descriptor(raw):return dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
def regular(path,missing=False):
    path=Path(path)
    need(path.is_absolute() and not any(p.is_symlink() for p in (path,*path.parents)),'alias source/payload refused: '+str(path))
    try:before=path.lstat()
    except FileNotFoundError:
        if missing:return None
        raise
    need(stat.S_ISREG(before.st_mode) and before.st_nlink==1,'single regular source/payload required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        held=os.fstat(stream.fileno());raw=stream.read();after=os.fstat(stream.fileno())
    named=path.lstat()
    need((before.st_dev,before.st_ino)==(held.st_dev,held.st_ino)==(named.st_dev,named.st_ino) and
         (held.st_size,held.st_mtime_ns)==(after.st_size,after.st_mtime_ns)==(named.st_size,named.st_mtime_ns),
         'source changed while read')
    return raw
def payloads():
    raw=regular(HERE/'source_states.json')
    need(hashlib.sha256(raw).hexdigest()==MANIFEST_SHA256,'fixed product manifest changed')
    m=json.loads(raw)
    need(m['schema']=='audio-onset579-product-source-v5' and m['files']==FILES and m['projects']==HEADS and
         m['previous_epochs']==PREVIOUS_EPOCHS and m['migration']==MIGRATION and m['legacy_projection']==LEGACY and
         m['implementation_prerequisites']==IMPLEMENTATION,
         'manifest differs from fixed code vector')
    review_raw=regular(HERE/'implementation_review.json')
    need(hashlib.sha256(review_raw).hexdigest()==IMPLEMENTATION_MANIFEST_SHA256 and json.loads(review_raw)==IMPLEMENTATION,
         'fixed actual clock implementation review changed')
    result={}
    for name,row in FILES.items():
        final=regular(HERE/'files'/name);need(descriptor(final)==row['after'],'fixed final payload changed: '+name)
        old=regular(HERE/'before'/name,True)
        need((descriptor(old) if old is not None else None)==row['before'],'fixed before payload changed: '+name)
        result[name]=(old,final)
    return result
def project_heads(root):
    for name,head in HEADS.items():
        path=root/name
        need(not path.is_symlink() and (path/'.git').exists(),'actual pinned Git project required: '+name)
        p=subprocess.run(['git','-C',str(path),'rev-parse','HEAD'],capture_output=True,text=True,check=False)
        need(p.returncode==0 and p.stdout.strip()==head,'actual project HEAD differs: '+name)
def implementation_snapshot(root):
    # Actual full source root only. Legacy sparse views never call this guard.
    project=root/IMPLEMENTATION['project']
    need(not project.is_symlink() and (project/'.git').exists(),'actual reviewed kernel project required')
    row=subprocess.run(['git','-C',str(project),'rev-parse','HEAD'],capture_output=True,text=True,check=False)
    need(row.returncode==0 and row.stdout.strip()==IMPLEMENTATION['head'],'actual reviewed kernel HEAD differs')
    result={}
    for name,expected in IMPLEMENTATION['files'].items():
        path=root/name;raw=regular(path);st=path.lstat()
        need(descriptor(raw)==expected,'actual clock implementation prerequisite differs: '+name)
        result[name]=(st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_size,st.st_mtime_ns,st.st_ctime_ns,expected)
    return result

def implementation_unchanged(root,previous):
    need(implementation_snapshot(root)==previous,'read-only clock source prerequisite changed during operation')

def observed(root):
    seen={}
    for name in FILES:
        raw=regular(root/name,True);seen[name]=None if raw is None else descriptor(raw)
    return seen

def classify(seen,allow_previous=False):
    if all(seen[n]==r['after'] for n,r in FILES.items()):return 'after'
    if all(seen[n]==r['before'] for n,r in FILES.items()):return 'before'
    if allow_previous:
        for epoch,previous in PREVIOUS_EPOCHS.items():
            if all(seen[n]==previous[n] for n in FILES):return epoch
    raise ValueError('unknown/partial onset579 source tuple; preserving every file')


CPU_GUARD_SHA='49090815ad90e2451a1d3b689dd965dbbb7d6f4228043cf31a2835e289451c60'
CPU_SOURCE_PATHS=('base/security/selinux_adapter/sepolicy/ohos_policy/drivers/peripheral/intelligent_voice/vendor/file.te', 'base/security/selinux_adapter/sepolicy/ohos_policy/drivers/peripheral/intelligent_voice/vendor/file_contexts', 'base/security/selinux_adapter/sepolicy/ohos_policy/drivers/peripheral/intelligent_voice/vendor/init.te', 'base/security/selinux_adapter/sepolicy/ohos_policy/drivers/peripheral/intelligent_voice/vendor/intell_voice_host.te', 'base/security/selinux_adapter/sepolicy/ohos_policy/multimedia/audio/public/type.te', 'base/security/selinux_adapter/sepolicy/ohos_policy/multimedia/audio/system/audio_server.te', 'base/security/selinux_adapter/sepolicy/ohos_policy/multimedia/audio/system/file_contexts', 'base/security/selinux_adapter/sepolicy/ohos_policy/multimedia/audio/system/init.te', 'drivers/peripheral/intelligent_voice/bundle.json', 'drivers/peripheral/intelligent_voice/hdi_service/engine/etc/intelligent_voice_engine.cfg', 'drivers/peripheral/intelligent_voice/intelligent_voice.gni', 'drivers/peripheral/intelligent_voice/passthrough/BUILD.gn', 'drivers/peripheral/intelligent_voice/passthrough/engine/engine_factory.cpp', 'drivers/peripheral/intelligent_voice/passthrough/engine/intell_voice_engine_manager.cpp', 'foundation/ai/intelligent_voice_framework/bundle.json', 'foundation/ai/intelligent_voice_framework/intell_voice_service.gni', 'foundation/ai/intelligent_voice_framework/services/intell_voice_engine/BUILD.gn', 'foundation/ai/intelligent_voice_framework/services/intell_voice_engine/server/enroll/enroll_engine.cpp', 'foundation/ai/intelligent_voice_framework/services/intell_voice_engine/server/wakeup/wakeup_engine.cpp', 'foundation/ai/intelligent_voice_framework/services/intell_voice_engine/server/wakeup/wakeup_engine_impl.cpp', 'foundation/ai/intelligent_voice_framework/services/intell_voice_engine/server/wakeup/wakeup_engine_impl.h', 'foundation/ai/intelligent_voice_framework/services/intell_voice_service/BUILD.gn', 'foundation/ai/intelligent_voice_framework/services/intell_voice_service/server/sa/intell_voice_service.cpp', 'foundation/multimedia/audio_framework/bundle.json', 'foundation/multimedia/audio_framework/config.gni', 'foundation/multimedia/audio_framework/frameworks/native/audioeffect/BUILD.gn', 'foundation/multimedia/audio_framework/frameworks/native/audioeffect/src/audio_effect_chain_manager.cpp', 'foundation/multimedia/audio_framework/services/audio_policy/BUILD.gn', 'foundation/multimedia/audio_framework/services/audio_policy/server/domain/effect/src/audio_spatialization_service.cpp', 'foundation/multimedia/audio_framework/services/audio_policy/server/infra/config/file/audio_effect_config.xml', 'foundation/multimedia/audio_framework/services/audio_service/etc/audio_server.cfg')

def media_predecessor(root):
    # Only the complete fixed CPU voice/spatial successor may project back to
    # this unchanged original whole Onset contract. No actual source is edited.
    path=PATCH_ROOT/'common/drivers/peripheral/intelligent_voice/cpu_provider/verify_source.py'
    need(hashlib.sha256(regular(path)).hexdigest()==CPU_GUARD_SHA,'fixed complete CPU source guard changed')
    spec=importlib.util.spec_from_file_location('_root_cpu_provider_source_guard579',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.preceding_files(root)
    if result is None:return {}
    need(type(result) is dict,'fixed CPU predecessor reader must return a source map')
    if not result:return {}
    need(set(result)==set(CPU_SOURCE_PATHS) and
        all(type(name) is str and type(raw) is bytes for name,raw in result.items()),
        'complete exact31 predecessor vector, never a supplied single-file SHA')
    return result

def source_validation_observed(root):
    actual=observed(root);previous=media_predecessor(root)
    for name,raw in previous.items():
        if name in FILES:
            need(descriptor(raw)==FILES[name]['after'],'CPU successor must retain the original complete Onset predecessor')
            actual[name]=descriptor(raw)
    return actual

def state(root,require_after=False):
    actual=classify(source_validation_observed(root))
    need(not require_after or actual=='after','complete final onset579 source required')
    return actual

def publisher():
    need(hashlib.sha256(regular(PATCH_ROOT/'lib/guarded_source_vector579.py')).hexdigest()==
         'afb7560daa888493878e6d107baf1487f48c09fb6fe028fd89b331842e2b83ee',
         'fixed transactional publisher changed')
    sys.path.insert(0,str(PATCH_ROOT/'lib'))
    from guarded_source_vector579 import apply as publish_vector
    return publish_vector

def lock_file(root):
    directory=root/'.ohos-qemu-patches';need(not directory.is_symlink(),'linked source lock directory')
    directory.mkdir(exist_ok=True)
    return os.fdopen(os.open(directory/'audio-onset579.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),'a')

def migrate_locked(root,publish_vector,*,defer_unverified=False):
    # Explicit product preparation only; verify, legacy and packaging never enter.
    seen=observed(root)
    try:epoch=classify(seen,True)
    except ValueError:
        if defer_unverified:return 'defer_to_original_normal_hooks_NOT_verified'
        raise
    if epoch in ('before','after'):return epoch
    previous=PREVIOUS_EPOCHS[epoch];patch_row=MIGRATION['epochs'][epoch]
    managed=MIGRATION['managed_by_epoch'][epoch];readonly=MIGRATION['readonly_by_epoch'][epoch]
    patch=regular(HERE/patch_row['patch'])
    need(hashlib.sha256(patch).hexdigest()==patch_row['patch_sha256'],'fixed finite upgrade patch changed')
    # Same source-pinned publisher primitives. Record/stage all35; replace only
    # the exact epoch subset (ten or two). Other source identities stay unchanged.
    from guarded_source_vector579 import identity,matches,replace
    originals={}
    for name in FILES:
        path=root/name;raw=regular(path,True)
        originals[name]=None if raw is None else dict(bytes=raw,identity=identity(path))
    need(observed(root)==seen,'complete prior tuple changed during snapshot')
    with tempfile.TemporaryDirectory(prefix='audio-global579-upgrade-') as directory:
        staged=Path(directory)
        for name,original in originals.items():
            if original is not None:
                p=staged/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(original['bytes'])
        subprocess.run(['patch','--binary','--batch','--forward','--fuzz=0','-p1','-i',str(HERE/patch_row['patch'])],cwd=staged,check=True)
        need(classify(observed(staged))=='after' and {str(p.relative_to(staged)) for p in staged.rglob('*') if p.is_file()}==set(FILES),'complete staged final35 required')
        finals={name:regular(staged/name) for name in FILES}
    project_heads(root)
    for name,original in originals.items():need(matches(root/name,original),'source inode changed before upgrade: '+name)
    installed={};directories=[]
    try:
        for name in managed:
            p=root/name;original=originals[name]
            need(matches(p,original),'source raced during owned upgrade: '+name)
            missing=[];parent=p.parent
            while not parent.exists():missing.append(parent);parent=parent.parent
            for directory in reversed(missing):
                directory.mkdir();st=directory.lstat();directories.append((directory,(st.st_dev,st.st_ino)))
            replace(p,finals[name],original['identity'] if original is not None else None,installed,name)
        for name in readonly:
            need(matches(root/name,originals[name]),'readonly source raced during upgrade: '+name)
        project_heads(root);state(root,True)
    except BaseException as error:
        failures=[]
        for name in reversed(managed):
            try:
                p=root/name;original=originals[name]
                if matches(p,original):continue
                need(name in installed and p.exists() and identity(p)==installed[name] and regular(p)==finals[name],
                     'unknown concurrent source preserved: '+name)
                if original is None:p.unlink()
                else:replace(p,original['bytes'],original['identity'],{},name)
            except BaseException as rollback_error:failures.append(name+': '+str(rollback_error))
        for directory,inode in reversed(directories):
            try:
                st=directory.lstat();need(stat.S_ISDIR(st.st_mode) and (st.st_dev,st.st_ino)==inode,'owned source directory changed')
                directory.rmdir()
            except (OSError,ValueError):failures.append('owned source directory not empty: '+str(directory))
        if failures:raise RuntimeError('owned source rollback incomplete: '+'; '.join(failures)) from error
        need(observed(root)==previous,'full prior tuple changed; foreign bytes preserved')
        raise
    return 'after'


def migrate(root):
    payloads();project_heads(root);implementation=implementation_snapshot(root);publish_vector=publisher()
    with lock_file(root) as held:
        fcntl.flock(held,fcntl.LOCK_EX)
        actual=migrate_locked(root,publish_vector,defer_unverified=True)
    implementation_unchanged(root,implementation)
    return actual

def apply(root):
    payloads();project_heads(root);implementation=implementation_snapshot(root)
    need(hashlib.sha256(regular(HERE/'0001-product-source.patch')).hexdigest()=='0ac6cd001e2f93542a5976e49fa5b2c31260f2695b9df54f24bffa813aecfc91',
         'fixed complete publication patch changed')
    publish_vector=publisher()
    with lock_file(root) as held:
        fcntl.flock(held,fcntl.LOCK_EX)
        migrate_locked(root,publish_vector)
        value={'projects':HEADS,'files':{name:[row['before']['sha256'] if row['before'] is not None else None,
            row['after']['sha256']] for name,row in FILES.items()}}
        publish_vector(root,HERE,value)
        state(root,True)
    implementation_unchanged(root,implementation)
def legacy(root,name,operation):
    implementation=implementation_snapshot(root)
    # Finite source-owned enumeration. Neither JSON nor command data selects code.
    row=LEGACY[name];component=PATCH_ROOT/row['path']
    media_before=media_predecessor(root)
    for script,sha in row['script_sha256'].items():
        need(hashlib.sha256(regular(component/script)).hexdigest()==sha,'fixed legacy source guard changed')
    marker=[root/n for n,r in FILES.items() if r['before'] is None]
    installed=any(p.exists() for p in marker)
    if installed:
        payloads();project_heads(root);state(root,True)
    def argv(source,projected):
        if operation.startswith('gn'):
            need(name=='alsa','GN output only belongs to original ALSA component')
            return [sys.executable,str(component/'apply.py'),'--source-root',str(source),'--gn-arg',operation[-1]]
        if projected or operation=='verify':
            return [sys.executable,str(component/row['verify']),'--source-root',str(source),*row['verify_args']]
        return ['bash',str(component/row['apply']),'--source-root',str(source)]
    if not installed:
        # Original component retains its complete original/final/partial guards.
        subprocess.run(argv(root,False),check=True);implementation_unchanged(root,implementation);return
    with tempfile.TemporaryDirectory(prefix='audio-onset579-projection-') as name_tmp:
        projection=Path(name_tmp)
        for name_src in row['paths']:
            raw=media_before[name_src] if name_src in media_before else regular(root/name_src)
            # Actual final global vector is already checked. Reverse only this
            # component's known overlap, without mutating any real source file.
            if name_src in FILES:
                raw=regular(HERE/'before'/name_src)
                need(descriptor(raw)==FILES[name_src]['before'],'projection beforeimage differs')
            target=projection/name_src;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        print(json.dumps(dict(scope='source-only exact reverse projection',component=row['path'],actual_onset579='after',
            actual_heads=HEADS,legacy_guard_unchanged=True,onset_proven=False)),file=sys.stderr)
        subprocess.run(argv(projection,True),check=True)
    implementation_unchanged(root,implementation)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--action',choices=('apply','verify','legacy','migrate','rewind'),default='apply')
    p.add_argument('--component',choices=tuple(LEGACY));p.add_argument('--operation',choices=('apply','verify','gn0','gn1'))
    a=p.parse_args();root=Path(os.path.abspath(a.source_root));need(root.is_dir() and not root.is_symlink(),'actual source root required')
    if a.action=='legacy':
        need(a.component is not None and a.operation is not None,'finite legacy component and operation required')
        legacy(root,a.component,a.operation);return
    need(a.component is None and a.operation is None,'unexpected legacy selectors')
    payloads();project_heads(root);implementation=implementation_snapshot(root)
    if a.action=='migrate':
        actual=migrate(root)
        implementation_unchanged(root,implementation)
        print(json.dumps(dict(schema='audio-onset579-preparation-upgrade-result-v1',state=actual,
            manifest_sha256=MANIFEST_SHA256,preparation_complete=False,final_source_verified=False,
            normal_hooks_and_final_require_after_mandatory=True,compiled=False,new_QEMU_validated=False,onset_proven=False,
            full82=False,first_artifact_behavior_gate_passed=False),sort_keys=True))
        return
    if a.action=='rewind':
        payloads();project_heads(root);state(root,True);publish_vector=publisher()
        with lock_file(root) as held:
            fcntl.flock(held,fcntl.LOCK_EX);state(root,True)
            inverse={'projects':HEADS,'files':{n:[r['after']['sha256'],r['before']['sha256'] if r['before'] is not None else None] for n,r in FILES.items()}}
            publish_vector(root,HERE,inverse,reverse=True);need(state(root)=='before','complete original prefix required')
        implementation_unchanged(root,implementation)
        print('Exact original prefix restored; normal hooks/final source gate remain mandatory');return
    if a.action=='apply':apply(root)
    state(root,True)
    implementation_unchanged(root,implementation)
    print(json.dumps(dict(schema='audio-onset579-source-result-v1',projects=HEADS,state='after',
        manifest_sha256=MANIFEST_SHA256,files=FILES,compiled=False,new_QEMU_validated=False,
        onset_proven=False,full82=False,first_artifact_behavior_gate_passed=False),sort_keys=True))
if __name__=='__main__':main()
