# Research data attribution and transformation notice

Downloaded and transformed 2026-10-03 for an educational Fire Detection prototype.
Raw measurements are preserved locally in `raw/` (Git-ignored). `processed/` contains
selected channels, algorithm outputs and evaluation metrics, not untouched originals.
See `sources.json` for exact URLs, pinned Git revision, byte sizes and SHA-256 hashes;
see each experiment JSON for units, selected channels, splits and thresholds.

1. National Institute of Standards and Technology / Fire Research Division,
   [UL_NIST_Vents experimental data](https://github.com/firemodels/exp/tree/ae8a6fca191222d2c047903bdcf61fb49bfb3f41/UL_NIST_Vents).
   Test 1–4: extracted Time and T_upper; added causal trend forecasts and proxy evaluation.
   The firemodels repository's complete notice is reproduced below.
2. National Institute of Standards and Technology,
   [Localized Fire Tests of Steel Beams](https://doi.org/10.18434/mds2-1856).
   Test 7–9: extracted time, VD1 and tc17; added reference-based deformation signals.
   [NIST open data license](https://www.nist.gov/open/license).
3. Fu, Hanyuan / Université Gustave Eiffel, 2023,
   [Pedestrian inertial navigation dataset with wearable sensor](https://doi.org/10.57745/ZCBIIB),
   Recherche Data Gouv, version 2.1. [Etalab Open License 2.0](https://spdx.org/licenses/etalab-2.0.html).
   TEST 02–04: timestamp alignment, step detection, initial heading/step-length calibration,
   estimated trajectories and errors added. Ground-truth trajectories are foot-mounted INS estimates.
   Inner archive and README verified against the publisher's MD5 values.

A `walking_bundle.zip` download is dynamically packaged by the public Dataverse API;
its ZIP hash can differ when re-downloaded. The inner archive's publisher MD5 and
SHA-256 identify the actual measurements. Locally computed hashes are integrity
records, not claims that a publisher supplied those SHA-256 values.

These transformations are project work, not NIST/UL/GEOLOC endorsements or their prediction models.
UWB form examples are explicitly synthetic geometry, not part of the downloaded measurements.

## Complete notice from firemodels/exp LICENSE.md

NIST-developed software is provided by NIST as a public service. You may use, copy and distribute copies of the software in any medium, provided that you keep intact this entire notice. You may improve, modify and create derivative works of the software or any portion of the software, and you may copy and distribute such modifications or works. Modified works should carry a notice stating that you changed the software and should note the date and nature of any such change. Please explicitly acknowledge the National Institute of Standards and Technology as the source of the software.

NIST-developed software is expressly provided “AS IS.” NIST MAKES NO WARRANTY OF ANY KIND, EXPRESS, IMPLIED, IN FACT OR ARISING BY OPERATION OF LAW, INCLUDING, WITHOUT LIMITATION, THE IMPLIED WARRANTY OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT AND DATA ACCURACY. NIST NEITHER REPRESENTS NOR WARRANTS THAT THE OPERATION OF THE SOFTWARE WILL BE UNINTERRUPTED OR ERROR-FREE, OR THAT ANY DEFECTS WILL BE CORRECTED. NIST DOES NOT WARRANT OR MAKE ANY REPRESENTATIONS REGARDING THE USE OF THE SOFTWARE OR THE RESULTS THEREOF, INCLUDING BUT NOT LIMITED TO THE CORRECTNESS, ACCURACY, RELIABILITY, OR USEFULNESS OF THE SOFTWARE.

You are solely responsible for determining the appropriateness of using and distributing the software and you assume all risks associated with its use, including but not limited to the risks and costs of program errors, compliance with applicable laws, damage to or loss of data, programs or equipment, and the unavailability or interruption of operation. This software is not intended to be used in any situation where a failure could cause risk of injury or damage to property. The software developed by NIST employees is not subject to copyright protection within the United States.
