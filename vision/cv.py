#!/usr/bin/env python

#roslib.load_manifest('INSERT NAME HERE') # FOR FUTURE WORK
import roslib
import rospy
from std_msgs.msg import String
from sensor_msgs.msg import Image
from cv_bridge import CvBridge, CvBridgeError

import sys
import cv2
import math
import numpy as np
from collections import deque

# Color values in HSV
GREENLOWER = np.array([77,80,40])
GREENUPPER = np.array([102,255,255])

BLUELOWER = np.array([110, 80, 40])
BLUEUPPER = np.array([130, 255, 255])

# Determines noise clear for morph
KERNELOPEN = np.ones((5,5))
KERNELCLOSE = np.ones((5,5))

# Font details for display windows
FONTFACE = cv2.FONT_HERSHEY_SIMPLEX
FONTSCALE = 1
FONTCOLOR = (255, 255, 255)

MAXBLOCKS = 6
MAXQUEUE = 20

# Instatiated for each unique block, holds positioning data
class Block:
    def __init__(self, idnum):
        self.points = []
        self.trackpoints = deque(maxlen=MAXQUEUE)
        self.idnum = idnum
    
    def addPoint(self, x, y):
        if math.isnan(x) or math.isnan(y):
            print("Invalid coordinate format!")
            return
        # This should be pushed with rosbag
        self.points.append((x,y))
        self.x = x
        self.y = y
        self.trackpoints.appendleft((x,y))

    # Compute distance between self and a given point
    def euclideanDistance(self, x, y):
        return math.sqrt((x - self.x)**2 + (y - self.y)**2)

# Pull images from ROS node and process them
class BridgeImage:

    def __init__(self):
    
        self.bridge = CvBridge()
        self.im_pub = rospy.Publisher("processed_image", Image, queue_size=10)
        self.im_sub = rospy.Subscriber("image_raw", Image, self.callback)
        self.initframe = True
        
        # Instantiate/Initialize blocks based on max alloted
        self.blocks = []
        for i in range(MAXBLOCKS):
            self.blocks.append(Block(i))
    
    # Process each image
    def callback(self, data):

        try:
            cv_im = self.bridge.imgmsg_to_cv2(data, "bgr8")
        except CvBridgeError as e:
            print(e)
        
        self.block_detector(cv_im)

        cv2.imshow("processed_image", cv_im)
        cv2.waitKey(3)

        try:
            self.im_pub.publish(self.bridge.cv2_to_imgmsg(cv_im, "bgr8"))
        except CvBridgeError as e:
            print(e)

    # Perform 3d printed block detection with each image
    def block_detector(self, im):
        
        # Convert image to HSV
        imHSV = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
        
        # Mask out image and use morphology to clear of image 'debris'
        mask_green = cv2.inRange(imHSV, GREENLOWER, GREENUPPER)
        mask_green_open = cv2.morphologyEx(mask_green, cv2.MORPH_OPEN, KERNELOPEN)
        mask_green_close = cv2.morphologyEx(mask_green_open, cv2.MORPH_CLOSE, KERNELCLOSE)
    
        mask_blue = cv2.inRange(imHSV, BLUELOWER, BLUEUPPER)
        mask_blue_open = cv2.morphologyEx(mask_blue, cv2.MORPH_OPEN, KERNELOPEN)
        mask_blue_close = cv2.morphologyEx(mask_blue_open, cv2.MORPH_CLOSE, KERNELCLOSE)
    
        # Combine masks to keep all blocks in single view, distinction between blocks lost
        mask_final = mask_green_close + mask_blue_close
    
    
        _, conts, h = cv2.findContours(mask_final.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    
        cv2.drawContours(im, conts, -1, (255,255,0), 1)
        
        for i in range(len(conts)):
            x,y,w,h = cv2.boundingRect(conts[i])
            
            # BUG: if block is occluded, the next closest (incorrect) block will be appended
            # with coordinates, which causes issues when all blocks are back in view
            # two blocks sharing IDs
            if True: #len(conts) == len(self.blocks): # Hack to prevent append when occluded
                xc, yc = self.getCenter(x,y,w,h)
                
                # If initializing point values we don't want to compute distances 
                if self.initframe:
                    if i == len(conts) - 1:
                        self.initframe = False

                    print("Init block with first points")
                    self.blocks[i].addPoint(xc, yc)

                else:
                    # Get block index w/ shortest euclidean distance from contour center
                    index = np.argmin([block.euclideanDistance(xc, yc) for block in self.blocks])
                    
                    self.blocks[index].addPoint(xc, yc)
                    
                    # Display history from point queue
                    pts = self.blocks[index].trackpoints

                    for j in xrange(1, len(pts)):

                        if pts[j - 1] is None or pts[j] is None:
                            continue
                        
                        # Trailing points should decrease thickness
                        thickness = int(np.sqrt(MAXQUEUE / float(j + 1))*1.5)
                        cv2.line(im, pts[j - 1], pts[j], (0, 0, 255), thickness)
                    
                    cv2.rectangle(im, (x,y), (x+w, y+h), (0,0,255), 1)
                    cv2.putText(im, str(index + 1), (x, y+h), FONTFACE, FONTSCALE, FONTCOLOR)
            
            # For diagnostics
            print(x, y, w, h)
            
        # Display various views 
        cv2.imshow("Green Mask", mask_green_close)
        cv2.imshow("Blue Mask", mask_blue_close)
        cv2.imshow("Combined Mask", mask_final)
        cv2.imshow("Image", im)
        cv2.waitKey(10)

    # Centroid calculation
    def getCenter(self, x, y, w, h):
        return (((int)(x+0.5*w)), ((int)(y+0.5*h)))



def main(args):
    bi = BridgeImage()
    rospy.init_node('bridge_image', anonymous=True)
    try:
        rospy.spin()
    except KeyboardInterrupt:
        print("Exiting...")

    cv2.destroyAllWindows()

if __name__ == '__main__':
    main(sys.argv)

